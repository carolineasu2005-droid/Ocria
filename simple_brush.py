# -*- coding: utf-8 -*-
"""
BOSS 直聘推荐牛人自动刷简历 v4 —— 键盘翻页 + 智能邮件转发版

交互方案：
1. 启动时输入触发关键词规则（规则用 ; 分隔）和备选邮箱
2. 鼠标保持不动，脚本只执行一次左键点击打开第一位候选人
3. 后续全部用键盘右方向键（→）切换下一位候选人
4. 每位候选人详情页停留 12-18 秒（随机），期间随机滚动
5. 停留期间检测详情页内容，命中任意关键词规则则触发邮件转发
6. 转发完成后右键恢复键盘焦点，继续用右方向键翻页
7. 每 100 人自动 F5 刷新
8. ESC 停止 / 空格暂停
"""
import sys
import io
import os
import ctypes
from ctypes import wintypes
import time
import random
import math
import logging
import threading
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Dict, Optional, Tuple
import win32gui
import win32con
import win32clipboard
import win32process
import pyautogui
from pynput import keyboard

from ocr_calibration import (
    CalibrationCancelled,
    ScreenRegion,
    enable_windows_dpi_awareness,
    save_region_preview,
    select_screen_region,
)
from calibration_profiles import (
    CalibrationProfileError,
    compare_system_info,
    load_profile,
    load_profile_file,
    scan_profiles,
    screen_region_from_dict,
)
from calibration_template import main as calibration_template_main
from ocr_detector import (
    DYNAMIC_END_DEFAULT_MODE,
    DYNAMIC_END_VERSION,
    DetectionResult,
    DynamicEndConfig,
    MSSScreenCapture,
    OCRKeywordDetector,
    RapidOCRBackend,
    ScanObservation,
    ScreenFingerprint,
    classify_position,
    compare_screen_fingerprints,
    evaluate_detail_page_load,
)
from ocr_text import parse_keyword_rules
from ocr_candidate import CandidateOcrBuilder, R05_AGGREGATION_MODE
from ocr_similarity import (
    DEFAULT_OCR_SIMILARITY_CONFIG,
    R06_SIMILARITY_MODE,
)
from ocr_normalization import (
    DEFAULT_OCR_NORMALIZATION_CONFIG,
    NORMALIZATION_VERSION,
    canonical_normalization_config,
    config_with_effective_min_confidence,
    normalization_config_digest,
)
from ocr_records import CaptureStatus, CaptureType, RunStatus
from ocr_store import JsonlOcrRecordStore
from mouse_motion import (
    move_to_observable,
    windmouse_available,
    windmouse_unavailable_reason,
)

# ─── 命令行参数解析 ───────────────────────────────
def parse_args():
    """解析命令行参数"""
    args = {
        'keywords': '',
        'email': '',
        'duration_seconds': '',
        'no_forward': False,
        'no_batch_filter': False,
        'simple_mouse': False,
        'auto': False,
        'action_mode': None,
        'calibration_profile': '',
    }
    i = 1
    while i < len(sys.argv):
        if sys.argv[i] == '--keywords' and i + 1 < len(sys.argv):
            args['keywords'] = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == '--email' and i + 1 < len(sys.argv):
            args['email'] = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == '--duration-seconds':
            if i + 1 >= len(sys.argv):
                raise ValueError('--duration-seconds 缺少秒数')
            args['duration_seconds'] = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == '--no-forward':
            args['no_forward'] = True
            i += 1
        elif sys.argv[i] == '--no-batch-filter':
            args['no_batch_filter'] = True
            i += 1
        elif sys.argv[i] == '--simple-mouse':
            args['simple_mouse'] = True
            i += 1
        elif sys.argv[i] == '--auto':
            args['auto'] = True  # 跳过所有交互
            i += 1
        elif sys.argv[i] == '--calibration-profile':
            if i + 1 >= len(sys.argv):
                raise ValueError('--calibration-profile 缺少模板名称')
            args['calibration_profile'] = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == '--action-mode':
            if i + 1 >= len(sys.argv):
                raise ValueError('--action-mode 缺少 favorite 或 forward')
            mode = sys.argv[i + 1].strip().lower()
            if mode not in (ACTION_MODE_FAVORITE, ACTION_MODE_FORWARD):
                raise ValueError('--action-mode 只能是 favorite 或 forward')
            args['action_mode'] = mode
            i += 2
        else:
            i += 1
    return args


def is_noninteractive_startup(cli_args):
    """Return whether command-line options must bypass the startup menu."""
    return bool(
        cli_args.get('auto')
        or cli_args.get('keywords')
        or cli_args.get('calibration_profile')
    )

# 修复 Windows 终端 UTF-8 输出
try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
except Exception:
    pass  # PyInstaller 打包后可能无 buffer，静默忽略

# ─── 配置 ───────────────────────────────────────────
ACTION_MODE_FAVORITE = "favorite"
ACTION_MODE_FORWARD = "forward"

MIN_STAY_SECONDS = 12
MAX_STAY_SECONDS = 18
BATCH_SIZE = 100
REFRESH_WAIT_SECONDS = 5
CLICK_WAIT_SECONDS = 2
COUNTDOWN_SECONDS = 3
FILTER_OPEN_DELAY_MIN = 0.5
FILTER_OPEN_DELAY_MAX = 1.0
FILTER_OPTION_DELAY_MIN = 0.3
FILTER_OPTION_DELAY_MAX = 0.7
FILTER_RESULTS_DELAY_MIN = 2.0
FILTER_RESULTS_DELAY_MAX = 3.0

CALIBRATION_PROFILE_USAGE_NOTICE = (
    '调用校准模板前，请确保 Boss 页面窗口位置、大小、缩放状态与校准时基本一致。'
)
CALIBRATION_PROFILE_OFFSET_RISK_NOTICE = (
    '如果窗口位置、窗口大小或页面缩放发生变化，旧模板中的点击区域可能发生偏移，建议重新校准。'
)

# OCR 关键词检测
OCR_MAX_SCANS = 8
OCR_MIN_CONFIDENCE = 0.85
OCR_BOX_COUNT_THRESHOLD = 5
OCR_TEXT_LENGTH_THRESHOLD = 30
LOAD_RETRY_WAIT_SECONDS = 1.5
MAX_LOAD_RETRIES = 3
MAX_CONSECUTIVE_LOAD_RECOVERIES = 1
OCR_SCROLL_MIN_STEPS = 600
OCR_SCROLL_MAX_STEPS = 1000
OCR_SETTLE_SECONDS = 0.6
OCR_CONFIRMATION_SECONDS = 0.7
OCR_PREVIEW_PATH = Path('logs/ocr_calibration_preview.png')
R04_RULE_EVALUATION_MODE = "legacy_shadow"
DYNAMIC_END_CONFIG = DynamicEndConfig(mode="full")

# R01 candidate-switch verification
CANDIDATE_SWITCH_MAX_ACTIONS = 2
CANDIDATE_SWITCH_MAX_OBSERVATIONS_PER_ACTION = 6
CANDIDATE_SWITCH_STABLE_OBSERVATIONS = 2
CANDIDATE_SWITCH_OBSERVATION_WAIT_SECONDS = 0.8

CANDIDATE_SWITCH_PENDING = "switch_pending"
CANDIDATE_SWITCH_LOADING = "switch_loading"
CANDIDATE_SWITCH_OBSERVING = "switch_observing"
CANDIDATE_SWITCH_UNCHANGED = "switch_unchanged"
CANDIDATE_SWITCH_CONFIRMED = "switch_confirmed"
CANDIDATE_SWITCH_UNVERIFIABLE = "switch_unverifiable"
CANDIDATE_SWITCH_FAILED = "switch_failed"

# 滚动
SCROLL_PROBABILITY = 0.8
SCROLL_MIN_STEPS = 600
SCROLL_MAX_STEPS = 1000
SCROLL_MAX_TIMES = 3

# ─── 转发功能配置 ────────────────────────────────────
@dataclass(frozen=True)
class ForwardClickRegions:
    """Runtime click regions for the mail-forwarding workflow."""

    forward_icon: ScreenRegion
    email_tab: ScreenRegion
    input_box: ScreenRegion
    recent_email: ScreenRegion
    forward_button: ScreenRegion


@dataclass(frozen=True)
class BatchFilterRegions:
    """Runtime click regions for filtering and opening the first candidate."""

    first_candidate: ScreenRegion
    open_filter: ScreenRegion
    unseen_filter: ScreenRegion
    confirm_filter: ScreenRegion


@dataclass(frozen=True)
class CandidateSwitchContext:
    """Immutable fingerprints retained for one candidate switch."""

    formal_fingerprints: Tuple[ScreenFingerprint, ...]
    pre_switch_fingerprint: ScreenFingerprint


@dataclass(frozen=True)
class CandidateSwitchResult:
    """Pure terminal or intermediate candidate-switch result."""

    state: str
    action_attempt: int
    observation_attempt: int
    confirmed_observation: Optional[ScanObservation] = None
    failure_reason: Optional[str] = None


def is_comparable_screen_fingerprint(
    fingerprint: Optional[ScreenFingerprint],
) -> bool:
    """Return whether an R03 fingerprint can be compared exactly."""

    return compare_screen_fingerprints(fingerprint, fingerprint) is True


def extract_formal_fingerprints(
    result: Optional[DetectionResult],
) -> Tuple[ScreenFingerprint, ...]:
    """Return valid formal R03 fingerprints ordered by screen index."""

    if result is None:
        return ()

    indexed_fingerprints = []
    seen_indexes = set()
    for observation in result.observations:
        fingerprint = observation.fingerprint
        if not is_comparable_screen_fingerprint(fingerprint):
            continue

        screen_index = fingerprint.screen_index
        if screen_index is None:
            continue
        if (
            isinstance(screen_index, bool)
            or not isinstance(screen_index, int)
            or not 1 <= screen_index <= 8
        ):
            raise ValueError("formal fingerprint invariant failed")
        if screen_index in seen_indexes:
            raise ValueError("formal fingerprint invariant failed")

        seen_indexes.add(screen_index)
        indexed_fingerprints.append((screen_index, fingerprint))

    if len(indexed_fingerprints) > 8:
        raise ValueError("formal fingerprint invariant failed")

    indexed_fingerprints.sort(key=lambda item: item[0])
    return tuple(fingerprint for _, fingerprint in indexed_fingerprints)


def candidate_switch_references(
    context: CandidateSwitchContext,
) -> Tuple[ScreenFingerprint, ...]:
    """Return formal fingerprints followed by the pre-switch baseline."""

    if len(context.formal_fingerprints) > 8:
        raise ValueError("candidate switch context invariant failed")

    seen_indexes = set()
    for fingerprint in context.formal_fingerprints:
        screen_index = fingerprint.screen_index
        if (
            not is_comparable_screen_fingerprint(fingerprint)
            or isinstance(screen_index, bool)
            or not isinstance(screen_index, int)
            or not 1 <= screen_index <= 8
            or screen_index in seen_indexes
        ):
            raise ValueError("candidate switch context invariant failed")
        seen_indexes.add(screen_index)

    if (
        context.pre_switch_fingerprint.screen_index is not None
        or not is_comparable_screen_fingerprint(
            context.pre_switch_fingerprint
        )
    ):
        raise ValueError("candidate switch context invariant failed")

    return context.formal_fingerprints + (
        context.pre_switch_fingerprint,
    )


def matches_any_previous_fingerprint(
    current: Optional[ScreenFingerprint],
    previous: Tuple[ScreenFingerprint, ...],
) -> Optional[bool]:
    """Return whether current exactly matches any previous fingerprint."""

    if not previous:
        return None

    saw_unverifiable = False
    for fingerprint in previous:
        comparison = compare_screen_fingerprints(current, fingerprint)
        if comparison is True:
            return True
        if comparison is None:
            saw_unverifiable = True

    if saw_unverifiable:
        return None
    return False


def differs_from_all_previous_fingerprints(
    current: Optional[ScreenFingerprint],
    previous: Tuple[ScreenFingerprint, ...],
) -> Optional[bool]:
    """Return whether current is provably different from every previous page."""

    matches_any = matches_any_previous_fingerprint(current, previous)
    if matches_any is True:
        return False
    if matches_any is False:
        return True
    return None


def fingerprints_are_stable(
    left: Optional[ScreenFingerprint],
    right: Optional[ScreenFingerprint],
) -> Optional[bool]:
    """Return R03 exact-comparison stability for two observations."""

    return compare_screen_fingerprints(left, right)


def evaluate_candidate_switch_observation(
    load_ready: Optional[bool],
    current_fingerprint: Optional[ScreenFingerprint],
    previous_fingerprints: Tuple[ScreenFingerprint, ...],
    previous_ready_fingerprint: Optional[ScreenFingerprint],
    previous_relation: Optional[str],
) -> Tuple[str, Optional[str]]:
    """Classify one candidate-switch observation without side effects."""

    if load_ready is False:
        return CANDIDATE_SWITCH_LOADING, None
    if load_ready is None:
        return CANDIDATE_SWITCH_UNVERIFIABLE, None
    if (
        not previous_fingerprints
        or not is_comparable_screen_fingerprint(current_fingerprint)
    ):
        return CANDIDATE_SWITCH_UNVERIFIABLE, None

    matches_previous = matches_any_previous_fingerprint(
        current_fingerprint,
        previous_fingerprints,
    )
    if matches_previous is None:
        return CANDIDATE_SWITCH_UNVERIFIABLE, None

    current_relation = "old" if matches_previous else "new"
    if (
        previous_ready_fingerprint is not None
        and previous_relation == current_relation
        and fingerprints_are_stable(
            previous_ready_fingerprint,
            current_fingerprint,
        )
        is True
    ):
        if current_relation == "old":
            return CANDIDATE_SWITCH_UNCHANGED, current_relation
        return CANDIDATE_SWITCH_CONFIRMED, current_relation

    return CANDIDATE_SWITCH_OBSERVING, current_relation


def candidate_switch_action_budget_exhausted(action_attempt: int) -> bool:
    """Return whether the frozen two-action budget is exhausted."""

    return action_attempt >= CANDIDATE_SWITCH_MAX_ACTIONS


def candidate_switch_observation_budget_exhausted(
    observation_attempt: int,
) -> bool:
    """Return whether the frozen six-observation budget is exhausted."""

    return (
        observation_attempt
        >= CANDIDATE_SWITCH_MAX_OBSERVATIONS_PER_ACTION
    )


def candidate_switch_focus_recovery_allowed(
    state: str,
    action_attempt: int,
) -> bool:
    """Return whether one focus recovery and retry is permitted."""

    return (
        state == CANDIDATE_SWITCH_UNCHANGED
        and action_attempt == 1
    )


def candidate_switch_scan_allowed(state: str) -> bool:
    """Return whether formal scanning and counting are permitted."""

    return state == CANDIDATE_SWITCH_CONFIRMED


def region_around(x, y, radius):
    """Return the inclusive +/- radius around a point as a ScreenRegion."""
    if radius < 0:
        raise ValueError('点击区域半径不能为负数')
    return ScreenRegion(
        left=x - radius,
        top=y - radius,
        width=radius * 2 + 1,
        height=radius * 2 + 1,
    )


# 坐标由用户手动从 1920×1080 截图读出（2026-06-30 校准）
# 转发牛人图标（候选人详情页右上角最右边的第3个图标）
FORWARD_ICON_X   = 1670
FORWARD_ICON_Y   = 260
# 弹窗左侧"邮件转发" Tab（高亮蓝色）
EMAIL_TAB_X      = 700
EMAIL_TAB_Y      = 600
# 弹窗顶部邮箱输入框
INPUT_BOX_X      = 900
INPUT_BOX_Y      = 390
# "最近联系"区域右侧第一个邮箱标签
RECENT_EMAIL_X   = 1000
RECENT_EMAIL_Y   = 440
# 弹窗右下角"转发"按钮（绿色）
FORWARD_BTN_X    = 1210
FORWARD_BTN_Y    = 740
# 转发后右键恢复键盘焦点位置（详情页中央偏右）
RIGHT_CLICK_X    = 960
RIGHT_CLICK_Y    = 500
# 候选人详情页空白区域（转发处理函数退出前统一恢复焦点）
DEFAULT_FOCUS_RESTORE_REGION = ScreenRegion(
    left=400,
    top=350,
    width=101,
    height=51,
)

# 鼠标点击与转发步骤配置
FORWARD_CLICK_OFFSET = 5    # 点击位置随机偏移范围（像素）
FORWARD_MIN_DELAY   = 0.5   # 步骤间最短延迟（秒）
FORWARD_MAX_DELAY   = 1.5   # 步骤间最长延迟（秒）
FORWARD_MAX_CONSEC  = 5     # 连续转发上限（超出跳过）

# 单次鼠标移动参数
MOUSE_MOVE_MIN_DURATION = 0.20
MOUSE_MOVE_MAX_DURATION = 0.75
MOUSE_MOVE_BASE_DURATION = 0.18
MOUSE_MOVE_DISTANCE_DIVISOR = 1800.0
MOUSE_MOVE_SAMPLE_RATE = 60
MOUSE_MOVE_MIN_STEPS = 12
MOUSE_MOVE_MAX_STEPS = 45
MOUSE_MOVE_SHORT_DISTANCE = 8.0
MOUSE_MOVE_CURVE_MIN_DISTANCE = 40.0
MOUSE_MOVE_CURVE_RATIO_MIN = 0.04
MOUSE_MOVE_CURVE_RATIO_MAX = 0.10
MOUSE_MOVE_CURVE_OFFSET_MIN = 4.0
MOUSE_MOVE_CURVE_OFFSET_MAX = 40.0
MOUSE_MOVE_JITTER_MIN = 0.5
MOUSE_MOVE_JITTER_MAX = 1.5

DEFAULT_FORWARD_CLICK_REGIONS = ForwardClickRegions(
    forward_icon=region_around(FORWARD_ICON_X, FORWARD_ICON_Y, 5),
    email_tab=region_around(EMAIL_TAB_X, EMAIL_TAB_Y, 5),
    input_box=region_around(INPUT_BOX_X, INPUT_BOX_Y, 3),
    recent_email=region_around(RECENT_EMAIL_X, RECENT_EMAIL_Y, 5),
    forward_button=region_around(FORWARD_BTN_X, FORWARD_BTN_Y, 5),
)

# 日志。Import 只装配 console；生产文件日志由脚本入口显式初始化，
# 避免 unittest/import 触碰真实运营日志。
DEFAULT_LOG_PATH = Path('logs/simple_brush.log')
_FILE_LOG_FORMAT = '%(asctime)s [%(levelname)s] %(message)s'
_CONSOLE_HANDLER_MARKER = '_bossocr_console_handler'
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def configure_file_logging(log_path=DEFAULT_LOG_PATH):
    """Install one explicit root FileHandler and return it.

    Calling this function repeatedly for the same resolved path is idempotent.
    Tests must pass a temporary path and close the returned handler with
    ``close_file_logging()``.  Importing this module never calls this function.
    """

    resolved_path = Path(log_path).resolve()
    root_logger = logging.getLogger()
    for handler in root_logger.handlers:
        if not isinstance(handler, logging.FileHandler):
            continue
        try:
            handler_path = Path(handler.baseFilename).resolve()
        except (AttributeError, OSError, TypeError, ValueError):
            continue
        if handler_path == resolved_path:
            root_logger.setLevel(logging.INFO)
            return handler

    resolved_path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(
        resolved_path,
        mode='a',
        encoding='utf-8',
    )
    handler.setFormatter(logging.Formatter(_FILE_LOG_FORMAT))
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)
    return handler


def close_file_logging(handler):
    """Remove, flush, and close a handler returned by configure_file_logging."""

    root_logger = logging.getLogger()
    if handler in root_logger.handlers:
        root_logger.removeHandler(handler)
    try:
        handler.flush()
    finally:
        handler.close()


console = next(
    (
        handler
        for handler in logger.handlers
        if getattr(handler, _CONSOLE_HANDLER_MARKER, False)
    ),
    None,
)
if console is None:
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(logging.Formatter(
        '%(asctime)s %(message)s',
        datefmt='%H:%M:%S',
    ))
    setattr(console, _CONSOLE_HANDLER_MARKER, True)
    logger.addHandler(console)

# ─── 运行时状态 ─────────────────────────────────────
stop_event = False
stop_reason = None
paused = False
run_duration_seconds = 0
simple_mouse_enabled = False
_windmouse_unavailable_warning_logged = False

# 转发状态（全局）
forward_keywords = []       # 启动时解析完成的关键词规则列表
backup_email = ""           # 备选邮箱
forward_enabled = False     # 是否启用转发
forward_consecutive = 0     # 连续转发计数
no_forward_mode = False     # 只检测，不执行真实邮件转发
action_mode = ACTION_MODE_FORWARD  # 候选人命中后的处理模式

# 转发关键点击区域（仅在当前运行期间有效）
forward_click_regions = DEFAULT_FORWARD_CLICK_REGIONS
forward_click_calibration_requested = False
forward_click_calibration_attempted = False
forward_click_calibration_in_progress = False

# 候选人列表筛选与首位归位区域（仅在当前运行期间有效）
batch_filter_regions = None
batch_filter_calibration_requested = False
batch_filter_calibration_attempted = False
batch_filter_calibration_in_progress = False
batch_filter_enabled = False

# 焦点恢复区域状态（仅在当前运行期间有效）
focus_restore_region = DEFAULT_FOCUS_RESTORE_REGION
focus_restore_calibration_requested = False
focus_restore_calibration_attempted = False
focus_restore_calibration_in_progress = False

# 收藏按钮区域状态（仅在当前运行期间有效）
favorite_button_region = None

# 校准模板选择状态（模板区域注入后供现有流程读取）
selected_calibration_profile = None

# OCR 状态（每次运行只初始化、校准一次）
ocr_backend = None
ocr_capture = None
ocr_detector = None
ocr_initialization_attempted = False
ocr_calibration_attempted = False
ocr_calibration_in_progress = False

# Stage-0 OCR persistence (one store per run, one builder per candidate).
ocr_record_store = None
current_candidate_builder = None
candidate_record_sequence = 0
recorded_observation_ids: Dict[int, ScanObservation] = {}


@dataclass(frozen=True)
class RecordedObservationResult:
    """One canonical record/save/classification result for a detector callback."""

    record: Optional[object]
    saved: bool
    position_decision: Optional[object] = None
    load_health: Optional[bool] = None
    ocr_health: Optional[bool] = None
    identity_health: Optional[bool] = None
    failure_stage: Optional[str] = None
    validation_code: Optional[str] = None
    sanitized_error_message: Optional[str] = None


_SAFE_RECORDING_VALIDATION_ERRORS = {
    "aggregation segment classifications are invalid": (
        "r05_segment_partition_invalid",
        "aggregation segment classifications are invalid",
    ),
    "document occurrence screen is invalid": (
        "candidate_occurrence_screen_invalid",
        "document occurrence screen is invalid",
    ),
    "similarity projection does not match nested result": (
        "r06_projection_mismatch",
        "similarity projection does not match nested result",
    ),
    "effective-new boolean does not match confirmed segments": (
        "r06_effective_new_boolean_mismatch",
        "effective-new boolean does not match confirmed segments",
    ),
}


def _safe_recording_error_fields(exc: Exception, failure_stage: str):
    """Return fixed, OCR-free diagnostics for persistence error context."""

    known = _SAFE_RECORDING_VALIDATION_ERRORS.get(str(exc))
    if known is not None:
        validation_code, message = known
    elif isinstance(exc, ValueError):
        validation_code, message = "validation_failed", "validation failed"
    else:
        validation_code, message = "operation_failed", "operation failed"
    return {
        "failure_stage": failure_stage,
        "validation_code": validation_code,
        "sanitized_error_message": message,
    }


def create_ocr_record_store():
    """Create the best-effort stage-0 store for one application run."""

    config = config_with_effective_min_confidence(
        DEFAULT_OCR_NORMALIZATION_CONFIG,
        OCR_MIN_CONFIDENCE,
    )
    snapshot = canonical_normalization_config(config)
    return JsonlOcrRecordStore(
        action_mode=action_mode,
        max_screen_count=OCR_MAX_SCANS,
        normalization_version=NORMALIZATION_VERSION,
        ocr_min_confidence=OCR_MIN_CONFIDENCE,
        normalization_config_version=config.normalization_config_version,
        normalization_config_digest=normalization_config_digest(snapshot),
        effective_min_confidence=config.effective_min_confidence,
        normalization_config=snapshot,
        rule_evaluation_mode=R04_RULE_EVALUATION_MODE,
        aggregation_mode=R05_AGGREGATION_MODE,
        similarity_mode=R06_SIMILARITY_MODE,
        similarity_config=DEFAULT_OCR_SIMILARITY_CONFIG,
        dynamic_end_version=DYNAMIC_END_VERSION,
        dynamic_end_mode=DYNAMIC_END_CONFIG.mode,
        dynamic_end_config=DYNAMIC_END_CONFIG.manifest_config(),
    )


def initialize_run_ocr_storage():
    """Initialize storage without allowing it to block the existing run."""

    global ocr_record_store
    try:
        ocr_record_store = create_ocr_record_store()
    except Exception as exc:
        ocr_record_store = None
        logger.warning(
            "event=ocr_store_factory_failed error_type=%s",
            type(exc).__name__,
        )
        return None
    if ocr_record_store.enabled:
        logger.info(
            "event=ocr_store_ready run_id=%s",
            ocr_record_store.run_id,
        )
    return ocr_record_store


def start_candidate_ocr_recording(
    candidate_in_batch: int,
    total_viewed: int,
):
    """Create the sole in-memory builder for the current candidate."""

    global current_candidate_builder
    global candidate_record_sequence
    global recorded_observation_ids
    if current_candidate_builder is not None:
        return current_candidate_builder
    if ocr_record_store is None or not ocr_record_store.enabled:
        return None
    candidate_record_sequence += 1
    current_candidate_builder = CandidateOcrBuilder(
        ocr_record_store.run_id,
        candidate_record_sequence,
        metadata={
            "candidate_in_batch": candidate_in_batch,
            "total_viewed_before": total_viewed,
        },
        aggregation_mode=R05_AGGREGATION_MODE,
        similarity_mode=R06_SIMILARITY_MODE,
        similarity_config=DEFAULT_OCR_SIMILARITY_CONFIG,
    )
    recorded_observation_ids = {}
    return current_candidate_builder


def _record_ocr_observation_result(
    observation: ScanObservation,
    capture_type,
    is_formal_screen: bool,
    screen_index: Optional[int],
):
    """Append one already-completed OCR result without triggering OCR again."""

    if current_candidate_builder is None or ocr_record_store is None:
        return RecordedObservationResult(None, False)
    observation_identity = id(observation)
    if observation_identity in recorded_observation_ids:
        return RecordedObservationResult(None, False)
    # One observation is consumed once even when its one build/save fails.
    recorded_observation_ids[observation_identity] = observation
    failure_stage = "screen_record_validation"
    record = None
    try:
        capture_type = (
            capture_type
            if isinstance(capture_type, CaptureType)
            else CaptureType(capture_type)
        )
        fingerprint = getattr(observation, "fingerprint", None)
        record = current_candidate_builder.build_screen_record(
            getattr(observation, "raw_items", ()),
            capture_type=capture_type,
            is_formal_screen=is_formal_screen,
            screen_index=screen_index,
            captured_at=(
                getattr(observation, "captured_at", None)
                or (
                    fingerprint.captured_at
                    if fingerprint is not None
                    else None
                )
            ),
            exact_hash=(
                fingerprint.exact_hash
                if fingerprint is not None
                else None
            ),
            fingerprint_version=(
                fingerprint.fingerprint_version
                if fingerprint is not None
                else None
            ),
            screen_id=getattr(observation, "screen_id", None),
            normalization=getattr(observation, "normalization", None),
            ocr_min_confidence=getattr(
                observation,
                "normalization_min_confidence",
                None,
            ),
            rule_comparison=getattr(
                observation,
                "rule_comparison",
                None,
            ),
            confidence_threshold_source="run_manifest",
            defer_commit=True,
        )
        failure_stage = "position_classification"
        position_decision = None
        if capture_type in (
            CaptureType.FORMAL_SCREEN,
            CaptureType.POSITION_CONFIRMATION,
        ):
            canonical_record = record
            try:
                load_health, _load_reason = evaluate_detail_page_load(
                    observation.ocr_box_count,
                    observation.ocr_text_length,
                    OCR_BOX_COUNT_THRESHOLD,
                    OCR_TEXT_LENGTH_THRESHOLD,
                )
            except (AttributeError, TypeError, ValueError):
                load_health = None
            ocr_health = (
                getattr(observation, "raw_items", None) is not None
                and isinstance(getattr(observation, "ocr_box_count", None), int)
                and isinstance(getattr(observation, "ocr_text_length", None), int)
            )
            dynamic_state = getattr(ocr_detector, "dynamic_end_state", None)
            previous_record = getattr(
                dynamic_state, "last_comparable_record", None,
            )
            position_decision = classify_position(
                previous_record,
                record,
                load_health=load_health,
                ocr_health=ocr_health,
                identity_health=(current_candidate_builder is not None),
            )
            # G3: canonical PositionDecision is the sole authority for final
            # capture type.  When the pre-classification says position_confirmation
            # but the decision says changed (effective new content / short_text_protected
            # with same exact hash), the capture must be promoted to a formal screen.
            # The same capture must only be saved once — no second build/save.
            if (
                capture_type == CaptureType.POSITION_CONFIRMATION
                and position_decision.position_status == "changed"
            ):
                capture_type = CaptureType.FORMAL_SCREEN
                promoted_screen_index = min(
                    8,
                    getattr(dynamic_state, "scan_slot_count", 0) + 1,
                )
                record = replace(
                    record,
                    capture_type=capture_type,
                    is_formal_screen=True,
                    screen_index=promoted_screen_index,
                )
                is_formal_screen = True
                screen_index = promoted_screen_index
            if capture_type == CaptureType.POSITION_CONFIRMATION:
                prediction_reason = (
                    "scroll_bottom_candidate"
                    if (
                        position_decision.position_status == "same"
                        and not position_decision.insufficient_evidence
                    ) else "position_confirmation_unresolved"
                )
            elif (
                position_decision.position_status == "same"
                and getattr(dynamic_state, "recovery_used", False)
            ):
                prediction_reason = "insufficient_evidence_after_recovery"
            else:
                prediction_reason = position_decision.prediction_reason
            record = replace(
                record,
                dynamic_end_version=DYNAMIC_END_VERSION,
                position_status=position_decision.position_status,
                page_change_status=position_decision.page_change_status,
                reference_screen_id=position_decision.reference_screen_id,
                is_position_confirmation=(
                    capture_type == CaptureType.POSITION_CONFIRMATION
                ),
                prediction_reason=prediction_reason,
            )
            record = current_candidate_builder.replace_latest_screen_record(
                canonical_record, record,
            )
        failure_stage = "store_screen"
        saved = bool(ocr_record_store.save_screen(record))
        if saved:
            current_candidate_builder.commit_screen_record(record)
        else:
            current_candidate_builder.discard_screen_record(record)
        return RecordedObservationResult(
            record,
            saved,
            position_decision,
            load_health=(load_health if position_decision is not None else None),
            ocr_health=(ocr_health if position_decision is not None else None),
            identity_health=(
                (current_candidate_builder is not None)
                if position_decision is not None else None
            ),
            failure_stage=(None if saved else failure_stage),
            validation_code=(None if saved else "store_save_failed"),
            sanitized_error_message=(
                None if saved else "screen save failed"
            ),
        )
    except Exception as exc:
        try:
            current_candidate_builder.discard_screen_record()
        except Exception:
            pass
        error_fields = _safe_recording_error_fields(exc, failure_stage)
        ocr_record_store.save_error(
            type(exc).__name__,
            "record_ocr_observation",
            {
                "candidate_record_id": (
                    current_candidate_builder.candidate_record_id
                ),
                "capture_type": str(capture_type),
                "screen_id": getattr(record, "screen_id", None),
                **error_fields,
            },
        )
        return RecordedObservationResult(
            None,
            False,
            failure_stage=error_fields["failure_stage"],
            validation_code=error_fields["validation_code"],
            sanitized_error_message=error_fields[
                "sanitized_error_message"
            ],
        )


def record_ocr_observation(
    observation: ScanObservation,
    capture_type,
    is_formal_screen: bool,
    screen_index: Optional[int],
):
    """Preserve the legacy record return for non-callback callers."""

    return _record_ocr_observation_result(
        observation,
        capture_type,
        is_formal_screen,
        screen_index,
    ).record


def record_detection_observation(
    observation: ScanObservation,
    capture_type: str,
    is_formal_screen: bool,
    screen_index: Optional[int],
) -> RecordedObservationResult:
    """Detector callback for formal scans and their existing confirmations."""

    return _record_ocr_observation_result(
        observation,
        capture_type,
        is_formal_screen,
        screen_index,
    )


def candidate_capture_status(detection_result):
    """Classify only the current fixed maximum-screen outcome."""

    if detection_result is not None:
        interrupt_reason = getattr(detection_result, "interrupt_reason", None)
        abort_reason = getattr(detection_result, "abort_reason", None)
        dynamic_end_reason = getattr(
            detection_result, "dynamic_end_reason", None,
        )
        if interrupt_reason in ("user_interrupted", "runtime_expired"):
            return CaptureStatus.INTERRUPTED, None
        if isinstance(abort_reason, str) and abort_reason:
            return CaptureStatus.ABORTED, None
        if dynamic_end_reason in (
            "scroll_bottom", "no_new_text", "max_screen_limit",
        ):
            return (
                CaptureStatus.COMPLETED_WITH_LIMIT,
                dynamic_end_reason,
            )
    if (
        detection_result is not None
        and not detection_result.confirmed_match
        and detection_result.scans_completed >= OCR_MAX_SCANS
    ):
        return CaptureStatus.COMPLETED_WITH_LIMIT, "max_screen_limit"
    return CaptureStatus.COMPLETED, "existing_flow_completed"


def _attach_dynamic_end_summary(document, detection_result):
    """Project the detector's bounded R07 facts into one candidate document."""

    if document is None or detection_result is None:
        return document
    mode = getattr(detection_result, "dynamic_end_mode", None)
    if mode is None:
        return document
    versions = dict(document.versions)
    versions["dynamic_end"] = DYNAMIC_END_VERSION
    fields = {
        "dynamic_end_mode": mode,
        "dynamic_end_reason": getattr(
            detection_result, "dynamic_end_reason", None,
        ),
        "abort_reason": getattr(detection_result, "abort_reason", None),
        "scan_slot_count": getattr(detection_result, "scan_slot_count", None),
        "normal_scroll_count": getattr(
            detection_result, "normal_scroll_count", None,
        ),
        "unique_position_count": getattr(
            detection_result, "unique_position_count", None,
        ),
        "ocr_attempt_count": getattr(
            detection_result, "ocr_attempt_count", None,
        ),
        "scroll_retry_count": getattr(
            detection_result, "scroll_retry_count", None,
        ),
        "focus_restore_count": getattr(
            detection_result, "focus_restore_count", None,
        ),
        "first_predicted_end_screen": getattr(
            detection_result, "first_predicted_end_screen", None,
        ),
        "first_predicted_end_reason": getattr(
            detection_result, "first_predicted_end_reason", None,
        ),
        "prediction_would_miss_content": getattr(
            detection_result, "prediction_would_miss_content", None,
        ),
        "prediction_would_miss_rule_match": getattr(
            detection_result, "prediction_would_miss_rule_match", None,
        ),
        "prediction_observation_complete": getattr(
            detection_result, "prediction_observation_complete", None,
        ),
        "prediction_evidence_complete": getattr(
            detection_result, "prediction_evidence_complete", None,
        ),
    }
    return replace(document, versions=versions, **fields)


def finalize_current_candidate_recording(
    capture_status: CaptureStatus,
    end_reason: Optional[str],
    abort_reason: Optional[str] = None,
    detection_result: Optional[DetectionResult] = None,
):
    """Save one candidate document and release its builder best-effort."""

    global current_candidate_builder
    global recorded_observation_ids
    builder = current_candidate_builder
    current_candidate_builder = None
    recorded_observation_ids = {}
    if builder is None:
        return None
    if abort_reason is None and detection_result is not None:
        abort_reason = (
            getattr(detection_result, "abort_reason", None)
            or getattr(detection_result, "interrupt_reason", None)
        )
    failure_stage = "candidate_validation"
    try:
        document = builder.finalize(
            capture_status,
            end_reason=end_reason,
            abort_reason=abort_reason,
        )
        document = _attach_dynamic_end_summary(document, detection_result)
        if ocr_record_store is not None:
            failure_stage = "store_candidate"
            ocr_record_store.save_candidate(
                document,
                owner_candidate_record_id=builder.candidate_record_id,
            )
        return document
    except Exception as exc:
        if ocr_record_store is not None:
            try:
                error_fields = _safe_recording_error_fields(
                    exc, failure_stage,
                )
                ocr_record_store.save_error(
                    type(exc).__name__,
                    "finalize_candidate",
                    {
                        "candidate_record_id": builder.candidate_record_id,
                        **error_fields,
                    },
                )
            except Exception:
                pass
        return None


def finalize_active_candidate_for_stop(
    exception_type: Optional[str] = None,
    detection_result: Optional[DetectionResult] = None,
):
    """Finalize an unfinished current candidate using existing stop state."""

    if current_candidate_builder is None:
        return None
    if exception_type is not None:
        return finalize_current_candidate_recording(
            CaptureStatus.ABORTED,
            None,
            exception_type,
            detection_result,
        )
    if stop_reason == "esc":
        return finalize_current_candidate_recording(
            CaptureStatus.INTERRUPTED,
            None,
            "user_interrupted",
            detection_result,
        )
    if stop_reason == "run_duration_elapsed":
        return finalize_current_candidate_recording(
            CaptureStatus.INTERRUPTED,
            None,
            "runtime_expired",
            detection_result,
        )
    return finalize_current_candidate_recording(
        CaptureStatus.ABORTED,
        None,
        stop_reason or "existing_flow_aborted",
        detection_result,
    )


def close_run_ocr_storage(status: RunStatus) -> None:
    """Close the run store without masking the existing exit path."""

    if ocr_record_store is None:
        return
    try:
        ocr_record_store.close(status)
    except Exception as exc:
        logger.warning(
            "event=ocr_store_close_failed error_type=%s",
            type(exc).__name__,
        )


# ─── 安全控制 ───────────────────────────────────────
_programmatic_esc = False  # 程序按的 ESC，不触发停止

def on_press(key):
    global stop_event, stop_reason, paused
    if key == keyboard.Key.esc:
        if _programmatic_esc:
            return True  # 程序触发的 ESC，忽略
        if (
            ocr_calibration_in_progress
            or focus_restore_calibration_in_progress
            or forward_click_calibration_in_progress
            or batch_filter_calibration_in_progress
        ):
            return True  # 交给 Tk 校准窗口处理，只取消校准，不停止浏览
        if stop_reason is None:
            stop_reason = 'esc'
            logger.info('⚡ 收到 ESC，准备停止')
        stop_event = True
        return False
    if key == keyboard.Key.space:
        paused = not paused
        logger.info(f'{"▶ 继续" if not paused else "⏸ 暂停"}')


listener = keyboard.Listener(on_press=on_press)
# 注意：listener.start() 在 run() 中调用，避免 exe 闪退


# ─── 用户交互输入 ───────────────────────────────────
def choose_startup_action():
    """Prompt an interactive user to run BossOCR, calibrate, or exit."""
    while True:
        raw = input(
            '\n请选择操作：\n\n'
            '1. 开始运行 BossOCR\n'
            '2. 创建或更新校准模板\n'
            '0. 退出\n> '
        ).strip()
        if raw == '1':
            return 'run'
        if raw == '2':
            return 'calibrate'
        if raw == '0':
            return 'exit'
        print('  输入无效，请输入 1、2 或 0。')


def launch_calibration_template():
    """Run the existing template generator and always return to this process."""
    try:
        calibration_template_main()
    except KeyboardInterrupt:
        print('\n校准模板流程已取消，未保存不完整模板。')
    except Exception as exc:
        print(f'\n校准模板启动失败：{exc}')
    finally:
        print('校准模板流程结束，返回启动菜单。')


def parse_duration_seconds(raw_value):
    """Parse an optional non-negative integer duration in seconds."""
    value = '' if raw_value is None else str(raw_value).strip()
    if not value:
        return 0
    if not value.isascii() or not value.isdigit():
        raise ValueError('运行时间必须为 0、正整数秒数或留空')
    return int(value)


def parse_action_mode_choice(raw):
    """Parse the interactive action-mode choice into an internal mode value."""
    value = '' if raw is None else str(raw).strip()
    if value == '1':
        return ACTION_MODE_FAVORITE
    if value == '2':
        return ACTION_MODE_FORWARD
    raise ValueError('请输入 1 或 2')


def prompt_action_mode():
    """Prompt until the user explicitly chooses favorite or forward mode."""
    while True:
        raw = input(
            '请选择候选人处理模式：\n'
            '1 = 收藏模式：点击收藏，不转发邮箱\n'
            '2 = 转发模式：执行原邮箱转发流程\n'
            '请输入 1 或 2：\n> '
        )
        try:
            return parse_action_mode_choice(raw)
        except ValueError:
            print('  输入无效，请输入 1 或 2。')


def prompt_calibration_profile_selection():
    """Let interactive users pick an existing calibration profile without loading it into flows."""
    global selected_calibration_profile
    selected_calibration_profile = None

    try:
        scan = scan_profiles()
    except Exception as exc:
        print(f'\n校准模板列表读取失败：{exc}')
        print('  将继续使用旧手动校准流程')
        return None

    for invalid in scan.invalid_profiles:
        print(f'\n跳过不可用校准模板：{invalid.path.name}')
        print(f'  原因：{invalid.error}')

    if not scan.profiles:
        print('  未发现可用校准模板，将继续使用旧手动校准流程')
        return None

    print('\n发现可用校准模板：')
    print(f'  {CALIBRATION_PROFILE_USAGE_NOTICE}')
    print(f'  {CALIBRATION_PROFILE_OFFSET_RISK_NOTICE}')
    for index, profile in enumerate(scan.profiles, start=1):
        print(
            f'  {index}. {profile.profile_name} '
            f'({profile.path.name}, 创建时间: {profile.created_at})'
        )
    print('  0. 不使用模板，走旧手动校准流程')
    print('  c. 查看如何新建或更新校准模板')

    while True:
        raw = input('请选择校准模板编号：\n> ').strip().lower()
        if raw in ('', '0'):
            print('  不使用校准模板，本次继续旧手动校准流程')
            return None
        if raw in ('c', 'create', 'new'):
            print('  可独立运行校准模板生成入口：python calibration_template.py')
            print('  本次继续旧手动校准流程')
            return None
        if raw.isascii() and raw.isdigit():
            index = int(raw)
            if 1 <= index <= len(scan.profiles):
                summary = scan.profiles[index - 1]
                try:
                    selected_calibration_profile = load_profile_file(summary.path)
                except CalibrationProfileError as exc:
                    print(f'  校准模板读取失败：{exc}')
                    print('  将继续使用旧手动校准流程')
                    selected_calibration_profile = None
                    return None
                decision = prompt_interactive_profile_system_match(
                    selected_calibration_profile
                )
                if decision == 'retry':
                    selected_calibration_profile = None
                    continue
                if decision == 'fallback':
                    selected_calibration_profile = None
                    return None
                print(f'  已选择校准模板：{selected_calibration_profile.profile_name}')
                return selected_calibration_profile
        print('  输入无效，请输入模板编号、0 或 c。')


def prompt_interactive_profile_system_match(profile):
    """Return use/retry/fallback after interactive system-info risk handling."""
    try:
        system_match = compare_system_info(profile.system_info)
    except Exception as exc:
        print(f'  校准模板系统信息校验失败：{exc}')
        print('  将继续使用旧手动校准流程')
        return 'fallback'

    if system_match.matches:
        return 'use'

    print('  当前环境与模板环境不一致。')
    print(f'  {CALIBRATION_PROFILE_USAGE_NOTICE}')
    print(f'  {CALIBRATION_PROFILE_OFFSET_RISK_NOTICE}')
    details = _format_system_info_mismatches(system_match.mismatches)
    if details:
        print(f'  不一致项：{details}')

    while True:
        raw = input(
            '请选择：\n'
            '1 = 继续使用该模板\n'
            'r = 重新选择模板\n'
            '0 = 不使用模板，走旧手动校准流程\n> '
        ).strip().lower()
        if raw == '1':
            return 'use'
        if raw in ('r', 'retry'):
            return 'retry'
        if raw in ('', '0'):
            return 'fallback'
        print('  输入无效，请输入 1、r 或 0。')


class CalibrationProfileRuntimeLoadError(ValueError):
    """Raised when a selected calibration profile cannot be applied safely."""


def _profile_region(profile, field_name):
    areas = getattr(profile, 'areas', None)
    if not isinstance(areas, dict):
        raise CalibrationProfileRuntimeLoadError('模板 areas 缺失或格式错误')
    if field_name not in areas:
        raise CalibrationProfileRuntimeLoadError(f'模板缺少必填区域字段：{field_name}')

    value = areas[field_name]
    if isinstance(value, ScreenRegion):
        if value.width <= 0 or value.height <= 0:
            raise CalibrationProfileRuntimeLoadError(
                f'模板区域尺寸非法：{field_name}'
            )
        return value

    try:
        return screen_region_from_dict(value)
    except Exception as exc:
        raise CalibrationProfileRuntimeLoadError(
            f'模板区域格式错误：{field_name}: {exc}'
        ) from exc


def load_calibration_profile_into_runtime(
    profile,
    *,
    no_batch_filter=False,
    action_mode_value=None,
):
    """Apply profile areas to existing runtime region structures atomically."""
    global forward_click_regions
    global batch_filter_regions
    global batch_filter_enabled
    global focus_restore_region
    global favorite_button_region
    global focus_restore_calibration_requested
    global forward_click_calibration_requested
    global batch_filter_calibration_requested

    mode = action_mode_value or action_mode

    loaded_forward_regions = ForwardClickRegions(
        forward_icon=_profile_region(profile, 'forward_icon'),
        email_tab=_profile_region(profile, 'email_tab'),
        input_box=_profile_region(profile, 'input_box'),
        recent_email=_profile_region(profile, 'recent_email'),
        forward_button=_profile_region(profile, 'forward_button'),
    )
    loaded_batch_regions = BatchFilterRegions(
        first_candidate=_profile_region(profile, 'first_candidate'),
        open_filter=_profile_region(profile, 'open_filter'),
        unseen_filter=_profile_region(profile, 'unseen_filter'),
        confirm_filter=_profile_region(profile, 'confirm_filter'),
    )
    loaded_focus_restore_region = _profile_region(profile, 'focus_restore_region')
    loaded_favorite_button_region = _profile_region(profile, 'favorite_button_region')

    if mode == ACTION_MODE_FORWARD and loaded_forward_regions is None:
        raise CalibrationProfileRuntimeLoadError('转发模式缺少转发点击区域')
    if mode == ACTION_MODE_FAVORITE and loaded_favorite_button_region is None:
        raise CalibrationProfileRuntimeLoadError('收藏模式缺少收藏按钮区域')

    forward_click_regions = loaded_forward_regions
    batch_filter_regions = loaded_batch_regions
    batch_filter_enabled = not no_batch_filter
    focus_restore_region = loaded_focus_restore_region
    favorite_button_region = loaded_favorite_button_region
    focus_restore_calibration_requested = False
    forward_click_calibration_requested = False
    batch_filter_calibration_requested = False

    logger.info(
        '✅ 已加载校准模板区域: %s',
        getattr(profile, 'profile_name', '(未命名模板)'),
    )
    if no_batch_filter:
        logger.info('--no-batch-filter 已启用：模板筛选区域已读取，但不会启用自动筛选归位')
    return True


def _format_system_info_mismatches(mismatches):
    details = []
    for key, values in mismatches.items():
        saved_value, current_value = values
        details.append(f'{key}: 模板={saved_value!r}, 当前={current_value!r}')
    return '; '.join(details)


def load_calibration_profile_for_noninteractive(
    profile_name,
    *,
    no_batch_filter=False,
    action_mode_value=None,
):
    """Load an explicitly named profile for non-interactive runs, failing closed."""
    global selected_calibration_profile

    name = '' if profile_name is None else str(profile_name).strip()
    if not name:
        return None

    try:
        profile = load_profile(name)
    except CalibrationProfileError as exc:
        raise ValueError(f'校准模板加载失败：{exc}') from exc

    try:
        system_match = compare_system_info(profile.system_info)
    except Exception as exc:
        raise ValueError(f'校准模板系统信息校验失败：{exc}') from exc

    if not system_match.matches:
        details = _format_system_info_mismatches(system_match.mismatches)
        raise ValueError(f'校准模板系统信息不匹配：{details}')

    try:
        load_calibration_profile_into_runtime(
            profile,
            no_batch_filter=no_batch_filter,
            action_mode_value=action_mode_value,
        )
    except Exception as exc:
        raise ValueError(f'校准模板加载失败：{exc}') from exc

    selected_calibration_profile = profile
    return profile


def keyword_rule_sources():
    """Return stable display strings for the configured keyword rules."""
    return [rule.source for rule in forward_keywords]


def get_user_input(
    keywords_str='',
    email_str='',
    duration_str='',
    auto=False,
    no_forward=False,
    no_batch_filter=False,
    action_mode_value=None,
    calibration_profile_name='',
):
    """
    获取关键词、备选邮箱和本次运行时间。
    auto=True、关键词或模板参数已传入时跳过交互。
    """
    global forward_keywords, backup_email, forward_enabled, run_duration_seconds
    global action_mode
    global focus_restore_calibration_requested
    global forward_click_calibration_requested
    global batch_filter_calibration_requested
    global selected_calibration_profile

    # ── 非交互模式（命令行传参或 --auto） ──
    if auto or keywords_str or calibration_profile_name:
        action_mode = action_mode_value or ACTION_MODE_FORWARD
        selected_calibration_profile = None
        focus_restore_calibration_requested = False
        forward_click_calibration_requested = False
        batch_filter_calibration_requested = False
        run_duration_seconds = parse_duration_seconds(duration_str)
        if keywords_str:
            forward_keywords = parse_keyword_rules(keywords_str)
            forward_enabled = bool(forward_keywords)
        else:
            forward_keywords = []
            forward_enabled = False
        backup_email = email_str
        loaded_profile = load_calibration_profile_for_noninteractive(
            calibration_profile_name,
            no_batch_filter=no_batch_filter,
            action_mode_value=action_mode,
        )
        print()
        print(f'  关键词规则数量: {len(forward_keywords)}')
        print(
            '  备选邮箱已提供: '
            f'{"是" if backup_email else "否"}'
        )
        if loaded_profile is not None:
            print(f'  校准模板: {loaded_profile.profile_name}')
        print(f'  运行时间: {run_duration_seconds or "持续运行"}')
        print()
        return

    # ── 交互模式 ──
    print()
    action_mode = prompt_action_mode()
    while True:
        raw = input(
            '请输入触发转发的关键词规则（关键词用英文双引号包裹，'
            '支持 and、or、not，规则用 ; 分隔，留空跳过转发）:\n> '
        ).strip()
        if not raw:
            forward_keywords = []
            forward_enabled = False
            print('  未设置关键词规则，转发功能已禁用')
            break
        try:
            forward_keywords = parse_keyword_rules(raw)
            forward_enabled = True
            print(f'  已录入 {len(forward_keywords)} 条关键词规则')
            break
        except ValueError as exc:
            print(f'  关键词规则格式错误：{exc}')
            print('  格式示例："Python"; "短剧" and not "销售"')

    if forward_enabled and action_mode == ACTION_MODE_FORWARD and not no_forward:
        backup_email = input('\n请输入备选邮箱（最近联系中无邮箱时兜底）:\n> ').strip()
        print(
            '  备选邮箱已提供: '
            f'{"是" if backup_email else "否"}'
        )
    else:
        backup_email = ""

    template_loaded = False
    selected_profile = prompt_calibration_profile_selection()
    if selected_profile is not None:
        try:
            template_loaded = load_calibration_profile_into_runtime(
                selected_profile,
                no_batch_filter=no_batch_filter,
                action_mode_value=action_mode,
            )
            print('  校准模板区域已加载，本次将使用模板参数')
            if no_batch_filter:
                print('  自动筛选归位已禁用，模板筛选区域不会启用')
        except Exception as exc:
            print(f'  校准模板加载失败：{exc}')
            print('  将继续使用旧手动校准流程')
            selected_calibration_profile = None
            template_loaded = False

    if template_loaded:
        while True:
            duration_raw = input('\n请输入本次运行时间（秒，留空或 0 表示持续运行）:\n> ')
            try:
                run_duration_seconds = parse_duration_seconds(duration_raw)
                break
            except ValueError as exc:
                print(f'  输入错误：{exc}')

        print(f'  运行时间: {run_duration_seconds or "持续运行"}')
        print()
        return

    if forward_enabled and action_mode == ACTION_MODE_FORWARD:
        calibrate_forward = input(
            '\n是否校准完整邮件转发点击区域（包含焦点恢复区域）？[y/N]\n> '
        ).strip().lower()
        calibrate_requested = calibrate_forward in ('y', 'yes')
        focus_restore_calibration_requested = calibrate_requested
        forward_click_calibration_requested = calibrate_requested
        if calibrate_requested:
            print('  将在第一位候选人详情页打开后进行完整转发点击区域校准')
        else:
            print('  完整转发点击将使用默认区域')
    else:
        focus_restore_calibration_requested = False
        forward_click_calibration_requested = False

    if no_batch_filter:
        batch_filter_calibration_requested = False
        print('  自动筛选归位已禁用，本次运行使用旧首位候选人流程')
    else:
        calibrate_batch_filter = input(
            '\n是否校准“最近没看过”筛选和首位候选人区域？[y/N]\n> '
        ).strip().lower()
        batch_filter_calibration_requested = calibrate_batch_filter in ('y', 'yes')
        if batch_filter_calibration_requested:
            print('  将在候选人列表页依次校准四个自动筛选归位区域')
        else:
            print('  本次运行使用旧首位候选人流程')

    while True:
        duration_raw = input('\n请输入本次运行时间（秒，留空或 0 表示持续运行）:\n> ')
        try:
            run_duration_seconds = parse_duration_seconds(duration_raw)
            break
        except ValueError as exc:
            print(f'  输入错误：{exc}')

    print(f'  运行时间: {run_duration_seconds or "持续运行"}')

    print()


# ─── 窗口操作 ───────────────────────────────────────

SUPPORTED_BOSS_BROWSERS = {
    'chrome.exe': 'Chrome',
    'msedge.exe': 'Edge',
}


def get_window_process_name(hwnd):
    """Return the executable name for a top-level Windows window."""
    handle = None
    try:
        _, process_id = win32process.GetWindowThreadProcessId(hwnd)
        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, process_id)
        if not handle:
            return ''
        size = wintypes.DWORD(32768)
        buffer = ctypes.create_unicode_buffer(size.value)
        if not ctypes.windll.kernel32.QueryFullProcessImageNameW(
            handle, 0, buffer, ctypes.byref(size)
        ):
            return ''
        return os.path.basename(buffer.value).lower()
    except Exception:
        return ''
    finally:
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)


def is_boss_browser_window(title, process_name):
    """Reject unrelated apps whose title merely contains the word BOSS."""
    return (
        process_name in SUPPORTED_BOSS_BROWSERS
        and ('BOSS' in title or 'zhipin' in title.lower())
    )


def bring_boss_foreground():
    """将 BOSS 直聘浏览器窗口置顶，优先 Chrome，其次 Edge。"""
    chrome_windows = []
    edge_windows = []

    def cb(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return True
        title = win32gui.GetWindowText(hwnd)
        process_name = get_window_process_name(hwnd)
        if is_boss_browser_window(title, process_name):
            candidate = (hwnd, title, SUPPORTED_BOSS_BROWSERS[process_name])
            if process_name == 'chrome.exe':
                chrome_windows.append(candidate)
            else:
                edge_windows.append(candidate)
        return True

    win32gui.EnumWindows(cb, None)

    if chrome_windows:
        hwnd, title, browser = chrome_windows[0]
    elif edge_windows:
        hwnd, title, browser = edge_windows[0]
    else:
        logger.error('❌ 找不到 BOSS 直聘 Chrome / Edge 窗口')
        return False

    if win32gui.IsIconic(hwnd):
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        time.sleep(0.3)

    try:
        win32gui.SetForegroundWindow(hwnd)
        time.sleep(0.5)
        logger.info(f'✅ BOSS {browser} 已置顶: {title}')
        return True
    except Exception as e:
        logger.error(
            '❌ 置顶失败 browser=%s error_type=%s', browser, type(e).__name__
        )
        return False


def bring_edge_foreground():
    """兼容旧调用入口。"""
    return bring_boss_foreground()


# ─── 基础工具 ───────────────────────────────────────

def safe_wait(seconds):
    """等待指定秒数，期间响应暂停/停止"""
    deadline = time.time() + seconds
    while time.time() < deadline:
        if stop_event:
            return False
        while paused and not stop_event:
            time.sleep(0.2)
        time.sleep(0.2)
    return True


def request_timed_stop():
    """Request a normal stop when the configured run duration expires."""
    global stop_event, stop_reason
    if stop_reason is None:
        stop_reason = 'run_duration_elapsed'
    stop_event = True


def request_load_failed_stop(
    candidate_in_batch,
    total_viewed,
    retry_number,
    reason,
    recovery_count,
    ocr_box_count='-',
    ocr_text_length='-',
):
    """Record an unrecoverable detail-load failure and request a safe stop."""
    global stop_event, stop_reason
    if stop_reason is not None:
        return
    logger.error(
        'event=detail_load_failed candidate_in_batch=%s total_viewed=%s '
        'attempt=retry retry_number=%s ocr_box_count=%s '
        'ocr_text_length=%s decision=error reason=%s state=load_failed '
        'recovery_count=%s next_action=safe_stop',
        candidate_in_batch,
        total_viewed,
        retry_number,
        ocr_box_count,
        ocr_text_length,
        reason,
        recovery_count,
    )
    if stop_reason is None:
        stop_reason = 'load_failed'
    stop_event = True


def log_candidate_switch_event(
    event: str,
    level: int,
    *,
    phase: Optional[str] = None,
    state: Optional[str] = None,
    action_attempt: Optional[int] = None,
    observation_attempt: Optional[int] = None,
    old_fingerprint_count: Optional[int] = None,
    compare_relation: Optional[str] = None,
    r02_ready: Optional[bool] = None,
    r02_reason: Optional[str] = None,
    failure_reason: Optional[str] = None,
    event_stop_reason: Optional[str] = None,
    candidate_in_batch: Optional[int] = None,
    total_viewed: Optional[int] = None,
    error_type: Optional[str] = None,
) -> None:
    """Write one fixed-field R01 event without page-derived content."""

    log_method = {
        logging.INFO: logger.info,
        logging.WARNING: logger.warning,
        logging.ERROR: logger.error,
    }[level]
    if r02_ready is True:
        ready_value = "true"
    elif r02_ready is False:
        ready_value = "false"
    else:
        ready_value = "-"

    message = (
        "event=%s phase=%s state=%s action_attempt=%s "
        "observation_attempt=%s old_fingerprint_count=%s "
        "current_hash=- compare_relation=%s r02_ready=%s "
        "r02_reason=%s failure_reason=%s stop_reason=%s "
        "candidate_in_batch=%s total_viewed=%s"
    )
    values = [
        event,
        phase or "-",
        state or "-",
        action_attempt if action_attempt is not None else "-",
        observation_attempt if observation_attempt is not None else "-",
        (
            old_fingerprint_count
            if old_fingerprint_count is not None
            else "-"
        ),
        compare_relation or "-",
        ready_value,
        r02_reason or "-",
        failure_reason or "-",
        event_stop_reason or "-",
        candidate_in_batch if candidate_in_batch is not None else "-",
        total_viewed if total_viewed is not None else "-",
    ]
    if error_type is not None:
        message += " error_type=%s"
        values.append(error_type)
    log_method(message, *values)


def request_candidate_switch_failed_stop(
    result: CandidateSwitchResult,
    candidate_in_batch: int,
    total_viewed: int,
) -> None:
    """Record the first R01 failure and request a safe stop."""

    global stop_event, stop_reason
    if stop_event or stop_reason is not None:
        return
    stop_reason = "candidate_switch_failed"
    stop_event = True
    log_candidate_switch_event(
        "candidate_switch_failed",
        logging.ERROR,
        phase=(
            "pre_switch"
            if result.action_attempt == 0
            else "post_next"
        ),
        state=result.state,
        action_attempt=result.action_attempt,
        observation_attempt=result.observation_attempt,
        failure_reason=result.failure_reason,
        event_stop_reason=stop_reason,
        candidate_in_batch=candidate_in_batch,
        total_viewed=total_viewed,
    )


def start_run_timer(duration_seconds):
    """Start the optional run timer and return it for later cancellation."""
    if duration_seconds <= 0:
        return None
    timer = threading.Timer(duration_seconds, request_timed_stop)
    timer.daemon = True
    timer.start()
    return timer


def human_delay(min_s=FORWARD_MIN_DELAY, max_s=FORWARD_MAX_DELAY):
    """随机延迟，模拟人类操作间隔"""
    delay = random.uniform(min_s, max_s)
    return safe_wait(delay)


def move_to_bezier_fallback(x, y):
    """Move to an exact target with the pre-WindMouse Bezier implementation."""
    target_x = int(round(x))
    target_y = int(round(y))
    start = pyautogui.position()
    start_x = float(start[0])
    start_y = float(start[1])
    delta_x = target_x - start_x
    delta_y = target_y - start_y
    distance = math.hypot(delta_x, delta_y)

    if distance == 0:
        pyautogui.moveTo(target_x, target_y, duration=0)
        return

    duration = min(
        MOUSE_MOVE_MAX_DURATION,
        max(
            MOUSE_MOVE_MIN_DURATION,
            MOUSE_MOVE_BASE_DURATION + distance / MOUSE_MOVE_DISTANCE_DIVISOR,
        ),
    )
    steps = min(
        MOUSE_MOVE_MAX_STEPS,
        max(MOUSE_MOVE_MIN_STEPS, round(duration * MOUSE_MOVE_SAMPLE_RATE)),
    )

    # Very short moves stay straight and stable. Moderate moves use a
    # degenerate straight Bezier without intermediate jitter.
    first_fraction = 1.0 / 3.0
    second_fraction = 2.0 / 3.0
    curve_offset = 0.0
    jitter_amplitude = 0.0
    if distance >= MOUSE_MOVE_CURVE_MIN_DISTANCE:
        first_fraction = random.uniform(0.25, 0.40)
        second_fraction = random.uniform(0.60, 0.75)
        curve_ratio = random.uniform(
            MOUSE_MOVE_CURVE_RATIO_MIN,
            MOUSE_MOVE_CURVE_RATIO_MAX,
        )
        curve_offset = min(
            MOUSE_MOVE_CURVE_OFFSET_MAX,
            max(MOUSE_MOVE_CURVE_OFFSET_MIN, distance * curve_ratio),
        )
        curve_offset *= random.choice((-1.0, 1.0))
        jitter_amplitude = random.uniform(
            MOUSE_MOVE_JITTER_MIN,
            MOUSE_MOVE_JITTER_MAX,
        )

    unit_x = delta_x / distance
    unit_y = delta_y / distance
    perpendicular_x = -unit_y
    perpendicular_y = unit_x
    control1_x = (
        start_x + delta_x * first_fraction + perpendicular_x * curve_offset
    )
    control1_y = (
        start_y + delta_y * first_fraction + perpendicular_y * curve_offset
    )
    control2_x = (
        start_x + delta_x * second_fraction + perpendicular_x * curve_offset
    )
    control2_y = (
        start_y + delta_y * second_fraction + perpendicular_y * curve_offset
    )
    step_interval = duration / steps

    for index in range(1, steps):
        progress = index / steps
        eased = 3.0 * progress ** 2 - 2.0 * progress ** 3
        inverse = 1.0 - eased
        point_x = (
            inverse ** 3 * start_x
            + 3.0 * inverse ** 2 * eased * control1_x
            + 3.0 * inverse * eased ** 2 * control2_x
            + eased ** 3 * target_x
        )
        point_y = (
            inverse ** 3 * start_y
            + 3.0 * inverse ** 2 * eased * control1_y
            + 3.0 * inverse * eased ** 2 * control2_y
            + eased ** 3 * target_y
        )

        if jitter_amplitude and distance >= MOUSE_MOVE_SHORT_DISTANCE:
            jitter_scale = math.sin(math.pi * progress)
            point_x += random.uniform(
                -jitter_amplitude,
                jitter_amplitude,
            ) * jitter_scale
            point_y += random.uniform(
                -jitter_amplitude,
                jitter_amplitude,
            ) * jitter_scale

        pyautogui.moveTo(int(round(point_x)), int(round(point_y)), duration=0)
        time.sleep(step_interval)

    # Never let curve rounding or intermediate jitter alter the click target.
    pyautogui.moveTo(target_x, target_y, duration=0)


def human_move_to(
    x,
    y,
    *,
    simple=None,
    region_width=None,
    region_height=None,
):
    """Move to an exact target using simple, WindMouse, or Bezier fallback."""
    global _windmouse_unavailable_warning_logged

    target_x = int(round(x))
    target_y = int(round(y))
    if simple is None:
        simple = simple_mouse_enabled
    if simple:
        pyautogui.moveTo(
            target_x,
            target_y,
            duration=random.uniform(0.15, 0.35),
        )
        return

    if not windmouse_available():
        if not _windmouse_unavailable_warning_logged:
            logger.warning(
                'WindMouse 不可用（%s），已回退到现有贝塞尔鼠标轨迹',
                windmouse_unavailable_reason(),
            )
            _windmouse_unavailable_warning_logged = True
        move_to_bezier_fallback(target_x, target_y)
        return

    try:
        if region_width is None and region_height is None:
            move_to_observable(target_x, target_y)
        else:
            move_to_observable(
                target_x,
                target_y,
                region_width=region_width,
                region_height=region_height,
            )
    except Exception as exc:
        logger.warning(
            'WindMouse 移动异常，已回退到现有贝塞尔鼠标轨迹：%s',
            exc,
        )
        move_to_bezier_fallback(target_x, target_y)


def human_click(
    x,
    y,
    offset=FORWARD_CLICK_OFFSET,
    *,
    region_width=None,
    region_height=None,
):
    """
    带随机偏移的人类化点击。
    点击位置在目标坐标的 ±offset 范围内随机抖动。
    按下时长随机 50-150ms，模拟人类手指停留。
    """
    tx = int(round(x + random.randint(-offset, offset)))
    ty = int(round(y + random.randint(-offset, offset)))
    if region_width is None and region_height is None:
        human_move_to(tx, ty)
    else:
        human_move_to(
            tx,
            ty,
            region_width=region_width,
            region_height=region_height,
        )
    time.sleep(random.uniform(0.03, 0.08))
    pyautogui.mouseDown(tx, ty)
    time.sleep(random.uniform(0.05, 0.15))
    pyautogui.mouseUp(tx, ty)


def random_point_in_region(region):
    """Return one point inside a screen region using half-open bounds."""
    if region.width <= 0 or region.height <= 0:
        raise ValueError('焦点恢复区域尺寸必须为正数')
    return (
        random.randint(region.left, region.left + region.width - 1),
        random.randint(region.top, region.top + region.height - 1),
    )


def random_point_in_inner_region(region, ratio=0.6):
    """Return one random point inside the centered portion of a screen region."""
    if region.width <= 0 or region.height <= 0:
        raise ValueError('点击区域尺寸必须为正数')
    if ratio <= 0 or ratio > 1:
        raise ValueError('内部区域比例必须大于 0 且不超过 1')

    margin_ratio = (1 - ratio) / 2
    inner_x_min = region.left + region.width * margin_ratio
    inner_x_max = region.left + region.width * (1 - margin_ratio)
    inner_y_min = region.top + region.height * margin_ratio
    inner_y_max = region.top + region.height * (1 - margin_ratio)
    return (
        random.uniform(inner_x_min, inner_x_max),
        random.uniform(inner_y_min, inner_y_max),
    )


def click_in_region(region):
    """Click one random point inside a region without adding a second offset."""
    x, y = random_point_in_region(region)
    human_click(
        x,
        y,
        offset=0,
        region_width=region.width,
        region_height=region.height,
    )


def perform_favorite_action():
    """Click the calibrated favorite button once, or fail safely if missing."""
    if favorite_button_region is None:
        logger.warning('收藏按钮区域未校准，跳过收藏点击以避免盲点')
        return False

    x, y = random_point_in_inner_region(favorite_button_region)
    human_click(
        x,
        y,
        offset=0,
        region_width=favorite_button_region.width,
        region_height=favorite_button_region.height,
    )
    time.sleep(0.5)
    restore_candidate_page_focus_after_favorite()
    return True


def restore_candidate_page_focus_after_favorite():
    """Restore detail-page focus after favorite through the shared helper."""
    return restore_candidate_detail_focus()


def restore_candidate_detail_focus():
    """Restore candidate-detail focus through the calibrated safe region."""
    for attempt in range(1, 3):
        try:
            focus_x, focus_y = random_point_in_region(focus_restore_region)
            human_click(
                focus_x,
                focus_y,
                offset=0,
                region_width=focus_restore_region.width,
                region_height=focus_restore_region.height,
            )
            human_delay(0.3, 0.5)
        except Exception as exc:
            logger.error(
                '❌ 详情页第 %s 次焦点恢复点击失败 error_type=%s',
                attempt,
                type(exc).__name__,
            )
    return True


def restore_candidate_page_focus():
    """Restore detail-page focus inside the calibrated OCR body region."""
    if ocr_detector is None:
        logger.warning('OCR 正文区域未就绪，跳过详情页焦点恢复')
        return False

    region = ocr_detector.region
    for _ in range(2):
        x, y = random_point_in_inner_region(region)
        human_click(
            x,
            y,
            offset=0,
            region_width=region.width,
            region_height=region.height,
        )
        time.sleep(0.15)
    return True


def get_clipboard_text():
    """读取剪贴板文本（CF_UNICODETEXT）。失败返回空字符串。"""
    try:
        win32clipboard.OpenClipboard()
        if win32clipboard.IsClipboardFormatAvailable(win32clipboard.CF_UNICODETEXT):
            data = win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)
        else:
            data = ""
        win32clipboard.CloseClipboard()
        return data
    except Exception:
        try:
            win32clipboard.CloseClipboard()
        except Exception:
            pass
        return ""


def type_text_human(text):
    """
    人类化文本输入。
    使用 pyautogui.typewrite 输入，字符间隔随机 0.03-0.08 秒。
    """
    for char in text:
        if stop_event:
            return False
        pyautogui.typewrite(char, interval=random.uniform(0.03, 0.08))
    return True


# ─── 关键词检测 ─────────────────────────────────────

class OCRInterrupted(RuntimeError):
    """Raised when Esc stops the run during an OCR wait or scroll."""


def initialize_ocr():
    """Initialize one RapidOCR engine for the entire process."""
    global ocr_backend, ocr_capture, ocr_initialization_attempted

    if ocr_initialization_attempted:
        return ocr_backend is not None and ocr_capture is not None
    ocr_initialization_attempted = True
    try:
        dpi_mode = enable_windows_dpi_awareness()
        ocr_backend = RapidOCRBackend()
        ocr_capture = MSSScreenCapture()
        logger.info(f'✅ OCR 初始化成功 (RapidOCR + ONNX Runtime, DPI={dpi_mode})')
        return True
    except Exception as exc:
        ocr_backend = None
        ocr_capture = None
        logger.exception(
            '❌ OCR 初始化失败，自动转发已安全禁用 error_type=%s',
            type(exc).__name__,
            exc_info=False,
        )
        return False


def ocr_wait(seconds):
    """OCR wait hook that keeps Esc and Space responsive."""
    if not safe_wait(seconds):
        raise OCRInterrupted('OCR scan interrupted by stop request')


def ocr_scroll_down():
    """Scroll down by the configured OCR scan distance."""
    if stop_event:
        raise OCRInterrupted('OCR scan interrupted by stop request')
    while paused and not stop_event:
        time.sleep(0.2)
    if stop_event:
        raise OCRInterrupted('OCR scan interrupted by stop request')
    steps = random.randint(OCR_SCROLL_MIN_STEPS, OCR_SCROLL_MAX_STEPS)
    logger.info(f'  OCR 有序向下滚动 {steps} 格')
    pyautogui.scroll(-steps)


def ocr_interrupt_reason():
    """Expose the existing stop fact to R07 without starting a new lifecycle."""

    if not stop_event:
        return None
    return "runtime_expired" if stop_reason == "run_duration_elapsed" else "user_interrupted"


def remaining_stay_seconds(target_seconds, started_at, now=None):
    """Return only the unspent part of the original candidate stay budget."""
    current = time.monotonic() if now is None else now
    return max(0.0, target_seconds - (current - started_at))


def ensure_ocr_region_calibrated():
    """Calibrate once after the first candidate detail is visible."""
    global ocr_detector, ocr_calibration_attempted, ocr_calibration_in_progress

    if ocr_detector is not None:
        return True
    if ocr_calibration_attempted:
        return False
    ocr_calibration_attempted = True

    if not initialize_ocr():
        logger.warning('🛡 因 OCR 不可用跳过关键词检测和转发')
        return False

    logger.info('请框选主显示器上的候选人详情正文区域；按 Esc 取消校准。')
    ocr_calibration_in_progress = True
    try:
        region = select_screen_region()
        preview = save_region_preview(region, OCR_PREVIEW_PATH, ocr_capture.capture)
    except CalibrationCancelled:
        logger.warning('🛡 OCR 校准已取消，本次运行禁用自动转发并继续浏览')
        return False
    except Exception as exc:
        logger.exception(
            '🛡 OCR 校准失败，本次运行禁用自动转发并继续浏览 '
            'error_type=%s',
            type(exc).__name__,
            exc_info=False,
        )
        return False
    finally:
        ocr_calibration_in_progress = False

    ocr_detector = OCRKeywordDetector(
        backend=ocr_backend,
        capture=ocr_capture,
        region=region,
        max_scans=OCR_MAX_SCANS,
        min_confidence=OCR_MIN_CONFIDENCE,
        scroll=ocr_scroll_down,
        wait=ocr_wait,
        settle_seconds=OCR_SETTLE_SECONDS,
        confirmation_seconds=OCR_CONFIRMATION_SECONDS,
        observation_callback=record_detection_observation,
        normalization_config=config_with_effective_min_confidence(
            DEFAULT_OCR_NORMALIZATION_CONFIG,
            OCR_MIN_CONFIDENCE,
        ),
        rule_evaluation_mode=R04_RULE_EVALUATION_MODE,
        dynamic_end_config=DYNAMIC_END_CONFIG,
        restore_focus=restore_candidate_page_focus,
        interrupt_reason_provider=ocr_interrupt_reason,
    )
    logger.info(
        '✅ OCR 校准完成: left=%s top=%s width=%s height=%s',
        region.left,
        region.top,
        region.width,
        region.height,
    )
    logger.info(f'校准预览已保存: {preview}')
    return True


def reset_focus_restore_calibration():
    """Reset focus restore calibration to its per-run defaults."""
    global focus_restore_region
    global focus_restore_calibration_requested
    global focus_restore_calibration_attempted
    global focus_restore_calibration_in_progress

    focus_restore_region = DEFAULT_FOCUS_RESTORE_REGION
    focus_restore_calibration_requested = False
    focus_restore_calibration_attempted = False
    focus_restore_calibration_in_progress = False


def reset_forward_click_calibration():
    """Reset forwarding click regions to their per-run defaults."""
    global forward_click_regions
    global forward_click_calibration_requested
    global forward_click_calibration_attempted
    global forward_click_calibration_in_progress

    forward_click_regions = DEFAULT_FORWARD_CLICK_REGIONS
    forward_click_calibration_requested = False
    forward_click_calibration_attempted = False
    forward_click_calibration_in_progress = False


def reset_batch_filter_calibration():
    """Reset batch filter calibration to its per-run disabled state."""
    global batch_filter_regions
    global batch_filter_calibration_requested
    global batch_filter_calibration_attempted
    global batch_filter_calibration_in_progress
    global batch_filter_enabled

    batch_filter_regions = None
    batch_filter_calibration_requested = False
    batch_filter_calibration_attempted = False
    batch_filter_calibration_in_progress = False
    batch_filter_enabled = False


def close_batch_filter_panel_after_calibration():
    """Best-effort close of the filter panel without stopping the run."""
    global _programmatic_esc

    _programmatic_esc = True
    try:
        pyautogui.press('esc')
    finally:
        _programmatic_esc = False


def ensure_batch_filter_regions_calibrated():
    """Calibrate all batch-filter navigation regions atomically once per run."""
    global batch_filter_regions
    global batch_filter_calibration_attempted
    global batch_filter_calibration_in_progress
    global batch_filter_enabled

    if not batch_filter_calibration_requested:
        return batch_filter_regions
    if batch_filter_calibration_attempted:
        return batch_filter_regions

    batch_filter_calibration_attempted = True
    batch_filter_calibration_in_progress = True
    panel_may_be_open = False
    panel_close_attempted = False

    try:
        first_candidate = select_screen_region(
            min_size=20,
            instruction='框选首位候选人卡片内部安全区域 · Esc 使用旧流程',
            subtitle='校准 1/4 · 只框选，不会打开候选人详情',
        )
        open_filter = select_screen_region(
            min_size=12,
            instruction='框选“打开筛选”按钮内部安全区域 · Esc 使用旧流程',
            subtitle='校准 2/4 · 程序将用该区域打开筛选面板',
        )

        # 点击可能已经改变页面，即使调用抛错也需要最佳努力关闭面板。
        panel_may_be_open = True
        click_in_region(open_filter)
        if not human_delay(0.5, 1.0):
            raise RuntimeError('打开筛选面板的等待被中断')

        unseen_filter = select_screen_region(
            min_size=12,
            instruction='框选“最近没看过”选项内部安全区域 · Esc 使用旧流程',
            subtitle='校准 3/4 · 只框选，不会选择该筛选项',
        )
        confirm_filter = select_screen_region(
            min_size=12,
            instruction='框选“筛选确定”按钮内部安全区域 · Esc 使用旧流程',
            subtitle='校准 4/4 · 只框选，不会应用筛选',
        )

        panel_close_attempted = True
        close_batch_filter_panel_after_calibration()
        panel_may_be_open = False

        calibrated_regions = BatchFilterRegions(
            first_candidate=first_candidate,
            open_filter=open_filter,
            unseen_filter=unseen_filter,
            confirm_filter=confirm_filter,
        )
        batch_filter_regions = calibrated_regions
        batch_filter_enabled = True
        logger.info('✅ 自动筛选归位区域校准完成')
    except CalibrationCancelled:
        batch_filter_regions = None
        batch_filter_enabled = False
        logger.warning('自动筛选归位区域校准已取消，本次运行使用旧流程')
    except Exception as exc:
        batch_filter_regions = None
        batch_filter_enabled = False
        logger.exception(
            '自动筛选归位区域校准失败，本次运行使用旧流程 '
            'error_type=%s',
            type(exc).__name__,
            exc_info=False,
        )
    finally:
        if panel_may_be_open and not panel_close_attempted:
            try:
                close_batch_filter_panel_after_calibration()
            except Exception as exc:
                logger.warning(
                    '校准后关闭筛选面板失败，本次运行使用旧流程 '
                    'error_type=%s',
                    type(exc).__name__,
                )
        batch_filter_calibration_in_progress = False

    return batch_filter_regions


def close_forward_dialog_after_calibration():
    """Close a possibly open forwarding dialog without stopping the run."""
    global _programmatic_esc

    _programmatic_esc = True
    try:
        pyautogui.press('esc')
    finally:
        _programmatic_esc = False


def ensure_forward_click_regions_calibrated():
    """Calibrate all forwarding click regions atomically once per run."""
    global forward_click_regions
    global forward_click_calibration_attempted
    global forward_click_calibration_in_progress

    if not forward_click_calibration_requested:
        return forward_click_regions
    if forward_click_calibration_attempted:
        return forward_click_regions

    forward_click_calibration_attempted = True
    forward_click_calibration_in_progress = True
    try:
        forward_icon = select_screen_region(
            min_size=12,
            instruction='框选详情页右上角“转发牛人”图标内部安全区域 · Esc 使用全部默认区域',
            subtitle='校准 1/5 · 程序将用该区域打开转发弹窗',
        )
        click_in_region(forward_icon)
        if not human_delay(0.8, 1.2):
            raise RuntimeError('打开转发弹窗的等待被中断')

        email_tab = select_screen_region(
            min_size=12,
            instruction='框选弹窗左侧“邮件转发” Tab 内部安全区域 · Esc 使用全部默认区域',
            subtitle='校准 2/5 · 程序将用该区域进入邮件转发界面',
        )
        click_in_region(email_tab)
        if not human_delay(0.5, 0.8):
            raise RuntimeError('切换邮件转发 Tab 的等待被中断')

        input_box = select_screen_region(
            min_size=12,
            instruction='框选邮箱输入框内部安全点击区域 · Esc 使用全部默认区域',
            subtitle='校准 3/5 · 只框选，不会输入内容',
        )
        recent_email = select_screen_region(
            min_size=12,
            instruction='框选“最近联系”中第一个邮箱标签内部安全区域 · Esc 使用全部默认区域',
            subtitle='校准 4/5 · 只框选，不会触发转发',
        )
        forward_button = select_screen_region(
            min_size=12,
            instruction='框选右下角“转发”按钮内部安全区域 · Esc 使用全部默认区域',
            subtitle='校准 5/5 · 只框选，程序绝不点击此按钮',
        )

        forward_click_regions = ForwardClickRegions(
            forward_icon=forward_icon,
            email_tab=email_tab,
            input_box=input_box,
            recent_email=recent_email,
            forward_button=forward_button,
        )
        logger.info('✅ 完整转发点击区域校准完成')
    except CalibrationCancelled:
        forward_click_regions = DEFAULT_FORWARD_CLICK_REGIONS
        logger.warning('完整转发点击区域校准已取消，本次运行全部使用默认区域')
    except Exception as exc:
        forward_click_regions = DEFAULT_FORWARD_CLICK_REGIONS
        logger.exception(
            '完整转发点击区域校准失败，本次运行全部使用默认区域 '
            'error_type=%s',
            type(exc).__name__,
            exc_info=False,
        )
    finally:
        try:
            close_forward_dialog_after_calibration()
        except Exception as exc:
            logger.warning(
                '校准后关闭转发弹窗失败，继续本次运行 error_type=%s',
                type(exc).__name__,
            )
        forward_click_calibration_in_progress = False

    return forward_click_regions


def ensure_focus_restore_region_calibrated():
    """Calibrate once when requested, falling back to the default region."""
    global focus_restore_region
    global focus_restore_calibration_attempted
    global focus_restore_calibration_in_progress

    if not focus_restore_calibration_requested:
        return focus_restore_region
    if focus_restore_calibration_attempted:
        return focus_restore_region

    focus_restore_calibration_attempted = True
    focus_restore_calibration_in_progress = True
    try:
        focus_restore_region = select_screen_region(
            min_size=20,
            instruction='拖动框选候选人详情页空白区域 · Esc 使用默认区域',
            subtitle='第一版仅支持主显示器',
        )
        logger.info(
            '✅ 焦点恢复区域校准完成: left=%s top=%s width=%s height=%s',
            focus_restore_region.left,
            focus_restore_region.top,
            focus_restore_region.width,
            focus_restore_region.height,
        )
    except CalibrationCancelled:
        focus_restore_region = DEFAULT_FOCUS_RESTORE_REGION
        logger.warning('焦点恢复区域校准已取消，本次运行使用默认区域')
    except Exception as exc:
        focus_restore_region = DEFAULT_FOCUS_RESTORE_REGION
        logger.exception(
            '焦点恢复区域校准失败，本次运行使用默认区域 error_type=%s',
            type(exc).__name__,
            exc_info=False,
        )
    finally:
        focus_restore_calibration_in_progress = False

    return focus_restore_region


def ensure_favorite_button_region_calibrated():
    """Calibrate the favorite button region for the current process only."""
    global favorite_button_region

    if favorite_button_region is not None:
        return favorite_button_region

    try:
        favorite_button_region = select_screen_region(
            min_size=12,
            instruction='框选“收藏”按钮内部安全区域 · Esc 取消收藏区域校准',
            subtitle='调用校准模板前，请确保 Boss 页面窗口位置、大小、缩放状态与校准时基本一致',
        )
        logger.info(
            '✅ 收藏按钮区域校准完成: left=%s top=%s width=%s height=%s',
            favorite_button_region.left,
            favorite_button_region.top,
            favorite_button_region.width,
            favorite_button_region.height,
        )
        return favorite_button_region
    except CalibrationCancelled:
        favorite_button_region = None
        logger.warning('收藏按钮区域校准已取消，本次不会盲点收藏按钮')
        return None
    except Exception as exc:
        favorite_button_region = None
        logger.exception(
            '收藏按钮区域校准失败，本次不会盲点收藏按钮 '
            'error_type=%s',
            type(exc).__name__,
            exc_info=False,
        )
        return None


def run_detail_load_gate(
    candidate_in_batch,
    total_viewed,
    recovery_count,
    recovery_available,
):
    """Run the bounded detail-page load checks at the current position."""
    for retry_number in range(MAX_LOAD_RETRIES + 1):
        state = 'loading' if retry_number == 0 else 'load_retrying'
        attempt = 'initial' if retry_number == 0 else 'retry'
        capture_type = (
            CaptureType.LOAD_CHECK
            if retry_number == 0
            else CaptureType.LOAD_RETRY
        )

        if retry_number > 0:
            if not safe_wait(LOAD_RETRY_WAIT_SECONDS):
                return None, None, retry_number, 'stopped'

        if stop_event:
            return None, None, retry_number, 'stopped'

        try:
            if ocr_detector is None:
                raise RuntimeError('OCR detector is not ready')
            observation = ocr_detector.capture_observation(1)
        except Exception:
            if stop_event:
                return None, None, retry_number, 'stopped'
            reason = 'ocr_error'
            ocr_box_count = '-'
            ocr_text_length = '-'
            decision = 'error'
            log = logger.warning
        else:
            if stop_event:
                record_ocr_observation(
                    observation,
                    capture_type,
                    False,
                    None,
                )
                return None, None, retry_number, 'stopped'
            try:
                loaded, reason = evaluate_detail_page_load(
                    observation.ocr_box_count,
                    observation.ocr_text_length,
                    OCR_BOX_COUNT_THRESHOLD,
                    OCR_TEXT_LENGTH_THRESHOLD,
                )
            except Exception:
                record_ocr_observation(
                    observation,
                    capture_type,
                    False,
                    None,
                )
                raise
            if loaded:
                return 'loaded', observation, retry_number, reason
            record_ocr_observation(
                observation,
                capture_type,
                False,
                None,
            )
            ocr_box_count = observation.ocr_box_count
            ocr_text_length = observation.ocr_text_length
            decision = 'not_loaded'
            log = logger.info

        has_retry = retry_number < MAX_LOAD_RETRIES
        can_recover = (
            recovery_available
            and recovery_count < MAX_CONSECUTIVE_LOAD_RECOVERIES
        )
        log(
            'event=detail_load_check candidate_in_batch=%s total_viewed=%s '
            'attempt=%s retry_number=%s ocr_box_count=%s '
            'ocr_text_length=%s decision=%s reason=%s state=%s '
            'recovery_count=%s next_action=%s',
            candidate_in_batch,
            total_viewed,
            attempt,
            retry_number,
            ocr_box_count,
            ocr_text_length,
            decision,
            reason,
            state,
            recovery_count,
            (
                'wait_and_retry'
                if has_retry
                else 'hard_refresh' if can_recover else 'safe_stop'
            ),
        )

    outcome = 'load_recovering' if can_recover else 'retries_exhausted'
    return outcome, None, MAX_LOAD_RETRIES, reason


def detect_keywords(
    first_observation: Optional[ScanObservation] = None,
) -> Tuple[bool, Optional[DetectionResult]]:
    """
    截取已校准的屏幕区域并执行最多 8 屏 OCR 精确匹配。
    返回关键词命中布尔值和同一个 DetectionResult；未检测时结果为 None。
    """
    if not forward_enabled or not forward_keywords:
        return False, None

    if not ensure_ocr_region_calibrated():
        logger.warning('🛡 OCR 未就绪，因安全原因跳过转发')
        return False, None

    logger.info(
        'event=ocr_rule_detection_started rule_count=%s',
        len(forward_keywords),
    )
    result = ocr_detector.detect(
        forward_keywords,
        first_observation=first_observation,
    )
    for sequence, observation in enumerate(result.observations, start=1):
        if observation is first_observation:
            continue
        phase = '二次确认' if sequence > 1 and (
            observation.scan_number == result.observations[sequence - 2].scan_number
        ) else '扫描'
        logger.info(
            '  OCR %s: 屏=%s 耗时=%.3fs 文字框=%s 命中=%s 规则序号=%s',
            phase,
            observation.scan_number,
            observation.elapsed_seconds,
            observation.item_count,
            bool(observation.matched_keyword),
            (
                observation.rule_comparison.legacy_rule_index
                if observation.rule_comparison is not None
                and observation.rule_comparison.legacy_rule_index is not None
                else '-'
            ),
        )

    if not result.success:
        logger.error(
            '🛡 OCR 错误，因安全原因跳过转发 error_type=detection_failed'
        )
        return False, result
    if result.error:
        logger.warning(
            '🛡 OCR 二次确认失败，因安全原因跳过转发 '
            'error_type=confirmation_failed'
        )
        return False, result
    if result.confirmed_match:
        logger.info('event=ocr_rule_confirmed matched=true')
        return True, result

    logger.info('  → OCR 最多 8 屏未确认命中，跳过转发')
    return False, result


# ─── 转发流程 ───────────────────────────────────────

def forward_one_candidate():
    """
    执行一次完整邮件转发流程。
    返回 True 表示转发成功，False 表示失败或跳过。
    """
    global forward_consecutive
    global _programmatic_esc

    try:
        # ── 检查连续转发上限 ──
        if forward_consecutive >= FORWARD_MAX_CONSEC:
            logger.warning(f'⚠ 连续转发已达上限 ({FORWARD_MAX_CONSEC} 次)，本次跳过')
            return False
        if stop_event:
            return False

        logger.info('📧 ────── 开始转发流程 ──────')

        # ── 步骤 1：点击"转发牛人"图标 ──
        logger.info(f'  [1/5] 点击"转发牛人"图标 →')
        click_in_region(forward_click_regions.forward_icon)
        if not human_delay(0.5, 1.5):
            return False

        # ── 步骤 2：点击"邮件转发" Tab ──
        logger.info(f'  [2/5] 点击"邮件转发"')
        click_in_region(forward_click_regions.email_tab)
        if not human_delay(0.5, 1.0):
            return False

        # ── 步骤 3：尝试填入邮箱 ──
        logger.info(f'  [3/5] 填入邮箱')
        # 先点"最近联系"中的邮箱标签
        click_in_region(forward_click_regions.recent_email)
        if not human_delay(0.3, 0.8):
            return False

        # 检测邮箱是否已填入
        click_in_region(forward_click_regions.input_box)
        time.sleep(0.1)
        if stop_event:
            return False
        pyautogui.hotkey('ctrl', 'a')
        time.sleep(0.05)
        if stop_event:
            return False
        pyautogui.hotkey('ctrl', 'c')
        time.sleep(0.08)
        if stop_event:
            return False
        box_text = get_clipboard_text().strip()

        if '@' in box_text and '.' in box_text:
            logger.info(
                'email_provided=true email_source=recent_contact'
            )
        else:
            logger.warning(
                'email_provided=false email_source=recent_contact'
            )
            if backup_email:
                # 手动输入备选邮箱
                logger.info(
                    'alternate_email_provided=true email_source=manual'
                )
                click_in_region(forward_click_regions.input_box)
                time.sleep(0.1)
                if stop_event:
                    return False
                pyautogui.hotkey('ctrl', 'a')
                time.sleep(0.05)
                if stop_event:
                    return False
                pyautogui.press('delete')
                time.sleep(0.05)
                if stop_event or not type_text_human(backup_email):
                    return False
                if not human_delay(0.3, 0.5):
                    return False
            else:
                logger.warning(
                    'alternate_email_provided=false email_source=manual '
                    'decision=skip_forward'
                )
                # 关闭弹窗（程序触发 ESC，不停止主循环）
                _programmatic_esc = True
                pyautogui.press('esc')
                _programmatic_esc = False
                return False

        # ── 步骤 4：点击"转发"按钮 ──
        if stop_event:
            return False
        logger.info(f'  [4/5] 点击"转发"按钮')
        click_in_region(forward_click_regions.forward_button)
        if not human_delay(1.0, 2.0):
            return False

        forward_consecutive += 1
        logger.info(f'📧 ✓ 转发完成！(连续转发 {forward_consecutive}/{FORWARD_MAX_CONSEC})')
        return True
    finally:
        # 只要进入转发处理函数，所有退出路径都统一恢复详情页焦点两次。
        restore_candidate_detail_focus()


# ─── 刷简历核心 ─────────────────────────────────────

def click_first_candidate(x, y):
    """在鼠标当前位置点击一次，打开第一位候选人详情"""
    if stop_event:
        return False
    logger.info(f'🖱️ 点击第一位候选人: ({x}, {y})')
    pyautogui.click(x, y, duration=0)
    return safe_wait(CLICK_WAIT_SECONDS)


def apply_batch_filter_and_open_first_candidate():
    """Apply the calibrated unseen filter and open the first candidate."""
    if stop_event:
        return False
    if not batch_filter_enabled or batch_filter_regions is None:
        logger.error('自动筛选归位区域未就绪，停止本轮运行')
        return False

    try:
        logger.info('🔎 打开候选人筛选面板')
        click_in_region(batch_filter_regions.open_filter)
        if not human_delay(FILTER_OPEN_DELAY_MIN, FILTER_OPEN_DELAY_MAX):
            return False

        if stop_event:
            return False
        logger.info('🔎 选择“最近没看过”')
        click_in_region(batch_filter_regions.unseen_filter)
        if not human_delay(FILTER_OPTION_DELAY_MIN, FILTER_OPTION_DELAY_MAX):
            return False

        if stop_event:
            return False
        logger.info('🔎 应用候选人筛选')
        click_in_region(batch_filter_regions.confirm_filter)
        if not human_delay(FILTER_RESULTS_DELAY_MIN, FILTER_RESULTS_DELAY_MAX):
            return False

        if stop_event:
            return False
        logger.info('🖱️ 点击筛选后的首位候选人')
        click_in_region(batch_filter_regions.first_candidate)
        return safe_wait(CLICK_WAIT_SECONDS)
    except Exception as exc:
        logger.exception(
            '自动筛选归位失败，停止本轮运行 error_type=%s',
            type(exc).__name__,
            exc_info=False,
        )
        return False


def open_first_candidate_for_batch(legacy_point=None):
    """Open the first candidate through the calibrated or legacy path."""
    if batch_filter_enabled:
        return apply_batch_filter_and_open_first_candidate()
    if legacy_point is None:
        logger.error('旧首位候选人坐标未就绪，停止本轮运行')
        return False
    return click_first_candidate(*legacy_point)


def human_scroll_once():
    """严格鼠标不动，仅在当前位置触发小幅度滚轮。"""
    if stop_event:
        return
    if random.random() > SCROLL_PROBABILITY:
        return

    times = random.randint(1, SCROLL_MAX_TIMES)
    direction = random.choice([-1, 1])

    logger.info(f'🖱️ 滚动 {times} 次，方向 {"下" if direction == -1 else "上"}')

    for _ in range(times):
        if stop_event:
            return
        steps = random.randint(SCROLL_MIN_STEPS, SCROLL_MAX_STEPS)
        if random.random() < 0.3:
            direction *= -1
        pyautogui.scroll(steps * direction)
        time.sleep(random.uniform(0.3, 1.0))


def view_candidate(
    index_in_batch: int,
    first_observation: Optional[ScanObservation] = None,
) -> Tuple[bool, Optional[DetectionResult]]:
    """
    浏览当前候选人。
    流程：检测关键词 → 命中则转发 → 停留 12-18 秒 + 滚动。
    """
    global forward_consecutive

    # OCR 扫描耗时计入原有 12-18 秒停留时间。
    stay = random.uniform(MIN_STAY_SECONDS, MAX_STAY_SECONDS)
    stay_started = time.monotonic()

    # ── 关键词检测（在浏览开始前） ──
    keyword_hit = False
    detection_result = None
    if forward_enabled and forward_keywords:
        keyword_hit, detection_result = detect_keywords(
            first_observation=first_observation
        )

        if stop_event:
            return False, detection_result

        if keyword_hit:
            if action_mode == ACTION_MODE_FAVORITE:
                perform_favorite_action()
            elif action_mode == ACTION_MODE_FORWARD:
                if no_forward_mode:
                    logger.info('🛡 --no-forward 已启用：保留 OCR 命中记录，禁止真实邮件转发')
                else:
                    forward_one_candidate()
            else:
                raise ValueError(f'未知候选人处理模式: {action_mode}')
        else:
            # 未命中关键词，重置连续转发计数
            forward_consecutive = 0

    # ── 停留浏览 ──
    status = '🔑' if keyword_hit else '👤'
    now = time.monotonic()
    elapsed = now - stay_started
    remaining_stay = remaining_stay_seconds(stay, stay_started, now)
    logger.info(
        f'{status} 第 {index_in_batch + 1}/{BATCH_SIZE} 位，'
        f'目标停留 {stay:.1f} 秒，OCR/处理已用 {elapsed:.1f} 秒，'
        f'剩余 {remaining_stay:.1f} 秒...'
    )

    end_time = time.monotonic() + remaining_stay
    while time.monotonic() < end_time:
        segment = random.uniform(2, 5)
        remaining = end_time - time.monotonic()
        if segment > remaining:
            segment = remaining
        if segment <= 0:
            break

        if not safe_wait(segment):
            return False, detection_result

        human_scroll_once()

    return True, detection_result


def next_candidate():
    """按右方向键切换到下一位候选人"""
    if stop_event:
        return False
    pyautogui.press('right')
    return safe_wait(0.5)


def prepare_candidate_switch_context(
    detection_result: Optional[DetectionResult],
    candidate_in_batch: int,
    total_viewed: int,
) -> Tuple[Optional[CandidateSwitchContext], Optional[str]]:
    """Capture one dedicated pre-switch baseline and build R01 context."""

    if stop_event:
        return None, "stopped"

    try:
        formal_fingerprints = extract_formal_fingerprints(detection_result)
    except ValueError:
        return None, "formal_fingerprint_invariant_failed"

    try:
        if ocr_detector is None:
            raise RuntimeError("OCR detector is not ready")
        observation = ocr_detector.capture_observation(1)
    except Exception as exc:
        log_candidate_switch_event(
            "candidate_switch_check",
            logging.WARNING,
            phase="pre_switch",
            state=CANDIDATE_SWITCH_UNVERIFIABLE,
            action_attempt=0,
            observation_attempt=1,
            old_fingerprint_count=len(formal_fingerprints),
            r02_reason="ocr_error",
            failure_reason="pre_switch_baseline_unavailable",
            event_stop_reason=stop_reason,
            candidate_in_batch=candidate_in_batch,
            total_viewed=total_viewed,
            error_type=type(exc).__name__,
        )
        if stop_event:
            return None, "stopped"
        return None, "pre_switch_baseline_unavailable"

    record_ocr_observation(
        observation,
        CaptureType.SWITCH_CHECK,
        False,
        None,
    )

    if stop_event:
        log_candidate_switch_event(
            "candidate_switch_check",
            logging.WARNING,
            phase="pre_switch",
            state=CANDIDATE_SWITCH_UNVERIFIABLE,
            action_attempt=0,
            observation_attempt=1,
            old_fingerprint_count=len(formal_fingerprints),
            r02_reason="stopped",
            event_stop_reason=stop_reason,
            candidate_in_batch=candidate_in_batch,
            total_viewed=total_viewed,
        )
        return None, "stopped"

    try:
        loaded, load_reason = evaluate_detail_page_load(
            observation.ocr_box_count,
            observation.ocr_text_length,
            OCR_BOX_COUNT_THRESHOLD,
            OCR_TEXT_LENGTH_THRESHOLD,
        )
    except (TypeError, ValueError) as exc:
        log_candidate_switch_event(
            "candidate_switch_check",
            logging.WARNING,
            phase="pre_switch",
            state=CANDIDATE_SWITCH_UNVERIFIABLE,
            action_attempt=0,
            observation_attempt=1,
            old_fingerprint_count=len(formal_fingerprints),
            r02_reason="invalid_r02_metrics",
            failure_reason="pre_switch_baseline_unavailable",
            candidate_in_batch=candidate_in_batch,
            total_viewed=total_viewed,
            error_type=type(exc).__name__,
        )
        return None, "pre_switch_baseline_unavailable"

    fingerprint = observation.fingerprint
    fingerprint_is_valid = (
        fingerprint is not None
        and fingerprint.screen_index is None
        and is_comparable_screen_fingerprint(fingerprint)
    )
    if not loaded or not fingerprint_is_valid:
        log_candidate_switch_event(
            "candidate_switch_check",
            logging.WARNING,
            phase="pre_switch",
            state=(
                CANDIDATE_SWITCH_LOADING
                if not loaded
                else CANDIDATE_SWITCH_UNVERIFIABLE
            ),
            action_attempt=0,
            observation_attempt=1,
            old_fingerprint_count=len(formal_fingerprints),
            r02_ready=loaded,
            r02_reason=load_reason,
            failure_reason="pre_switch_baseline_unavailable",
            candidate_in_batch=candidate_in_batch,
            total_viewed=total_viewed,
        )
        return None, "pre_switch_baseline_unavailable"

    context = CandidateSwitchContext(
        formal_fingerprints=formal_fingerprints,
        pre_switch_fingerprint=fingerprint,
    )
    try:
        references = candidate_switch_references(context)
    except ValueError:
        log_candidate_switch_event(
            "candidate_switch_check",
            logging.WARNING,
            phase="pre_switch",
            state=CANDIDATE_SWITCH_UNVERIFIABLE,
            action_attempt=0,
            observation_attempt=1,
            old_fingerprint_count=len(formal_fingerprints),
            r02_ready=True,
            r02_reason=load_reason,
            failure_reason="formal_fingerprint_invariant_failed",
            candidate_in_batch=candidate_in_batch,
            total_viewed=total_viewed,
        )
        return None, "formal_fingerprint_invariant_failed"
    log_candidate_switch_event(
        "candidate_switch_check",
        logging.INFO,
        phase="pre_switch",
        state=CANDIDATE_SWITCH_PENDING,
        action_attempt=0,
        observation_attempt=1,
        old_fingerprint_count=len(references),
        r02_ready=True,
        r02_reason=load_reason,
        candidate_in_batch=candidate_in_batch,
        total_viewed=total_viewed,
    )
    return context, None


def confirm_candidate_switch(
    context: CandidateSwitchContext,
    candidate_in_batch: int,
    total_viewed: int,
) -> Optional[CandidateSwitchResult]:
    """Confirm one bounded candidate switch with at most two next actions."""

    if stop_event:
        return None

    try:
        previous_fingerprints = candidate_switch_references(context)
    except ValueError:
        return CandidateSwitchResult(
            state=CANDIDATE_SWITCH_FAILED,
            action_attempt=0,
            observation_attempt=0,
            failure_reason="formal_fingerprint_invariant_failed",
        )

    action_attempt = 0
    while not candidate_switch_action_budget_exhausted(action_attempt):
        state = CANDIDATE_SWITCH_PENDING
        action_attempt += 1
        try:
            switched = next_candidate()
        except Exception:
            if stop_event:
                return None
            return CandidateSwitchResult(
                state=CANDIDATE_SWITCH_FAILED,
                action_attempt=action_attempt,
                observation_attempt=0,
                failure_reason="next_action_failed",
            )
        if not switched:
            if stop_event:
                return None
            return CandidateSwitchResult(
                state=CANDIDATE_SWITCH_FAILED,
                action_attempt=action_attempt,
                observation_attempt=0,
                failure_reason="next_action_failed",
            )

        previous_ready_fingerprint = None
        previous_relation = None
        saw_new = False
        saw_loading = False
        saw_unverifiable = False
        saw_capture_error = False
        all_observations_old = True

        for observation_attempt in range(
            1,
            CANDIDATE_SWITCH_MAX_OBSERVATIONS_PER_ACTION + 1,
        ):
            if observation_attempt > 1:
                if not safe_wait(CANDIDATE_SWITCH_OBSERVATION_WAIT_SECONDS):
                    if stop_event:
                        return None
                    return CandidateSwitchResult(
                        state=CANDIDATE_SWITCH_FAILED,
                        action_attempt=action_attempt,
                        observation_attempt=observation_attempt - 1,
                        failure_reason="observation_budget_exhausted",
                    )
            if stop_event:
                return None

            try:
                if ocr_detector is None:
                    raise RuntimeError("OCR detector is not ready")
                observation = ocr_detector.capture_observation(1)
            except Exception as exc:
                log_candidate_switch_event(
                    "candidate_switch_check",
                    logging.WARNING,
                    phase="post_next",
                    state=CANDIDATE_SWITCH_UNVERIFIABLE,
                    action_attempt=action_attempt,
                    observation_attempt=observation_attempt,
                    old_fingerprint_count=len(previous_fingerprints),
                    r02_reason="ocr_error",
                    event_stop_reason=stop_reason,
                    candidate_in_batch=candidate_in_batch,
                    total_viewed=total_viewed,
                    error_type=type(exc).__name__,
                )
                if stop_event:
                    return None
                saw_unverifiable = True
                saw_capture_error = True
                all_observations_old = False
                previous_ready_fingerprint = None
                previous_relation = None
                continue

            if stop_event:
                record_ocr_observation(
                    observation,
                    CaptureType.SWITCH_CHECK,
                    False,
                    None,
                )
                log_candidate_switch_event(
                    "candidate_switch_check",
                    logging.WARNING,
                    phase="post_next",
                    state=CANDIDATE_SWITCH_UNVERIFIABLE,
                    action_attempt=action_attempt,
                    observation_attempt=observation_attempt,
                    old_fingerprint_count=len(previous_fingerprints),
                    r02_reason="stopped",
                    event_stop_reason=stop_reason,
                    candidate_in_batch=candidate_in_batch,
                    total_viewed=total_viewed,
                )
                return None

            load_error_type = None
            try:
                load_ready, load_reason = evaluate_detail_page_load(
                    observation.ocr_box_count,
                    observation.ocr_text_length,
                    OCR_BOX_COUNT_THRESHOLD,
                    OCR_TEXT_LENGTH_THRESHOLD,
                )
            except (TypeError, ValueError) as exc:
                load_ready = None
                load_reason = "invalid_r02_metrics"
                load_error_type = type(exc).__name__

            current_fingerprint = observation.fingerprint
            if (
                current_fingerprint is not None
                and current_fingerprint.screen_index is not None
            ):
                current_fingerprint = None

            state, relation = evaluate_candidate_switch_observation(
                load_ready=load_ready,
                current_fingerprint=current_fingerprint,
                previous_fingerprints=previous_fingerprints,
                previous_ready_fingerprint=previous_ready_fingerprint,
                previous_relation=previous_relation,
            )
            if relation == "new":
                saw_new = True
            if relation != "old":
                all_observations_old = False
            if state == CANDIDATE_SWITCH_LOADING:
                saw_loading = True
            elif state == CANDIDATE_SWITCH_UNVERIFIABLE:
                saw_unverifiable = True

            if state != CANDIDATE_SWITCH_CONFIRMED:
                record_ocr_observation(
                    observation,
                    CaptureType.SWITCH_CHECK,
                    False,
                    None,
                )

            log_candidate_switch_event(
                "candidate_switch_check",
                (
                    logging.WARNING
                    if state in (
                        CANDIDATE_SWITCH_LOADING,
                        CANDIDATE_SWITCH_UNVERIFIABLE,
                    )
                    else logging.INFO
                ),
                phase="post_next",
                state=state,
                action_attempt=action_attempt,
                observation_attempt=observation_attempt,
                old_fingerprint_count=len(previous_fingerprints),
                compare_relation=relation,
                r02_ready=load_ready,
                r02_reason=load_reason,
                candidate_in_batch=candidate_in_batch,
                total_viewed=total_viewed,
                error_type=load_error_type,
            )

            if state == CANDIDATE_SWITCH_CONFIRMED:
                log_candidate_switch_event(
                    "candidate_switch_confirmed",
                    logging.INFO,
                    phase="post_next",
                    state=state,
                    action_attempt=action_attempt,
                    observation_attempt=observation_attempt,
                    old_fingerprint_count=len(previous_fingerprints),
                    compare_relation=relation,
                    r02_ready=load_ready,
                    r02_reason=load_reason,
                    candidate_in_batch=candidate_in_batch,
                    total_viewed=total_viewed,
                )
                return CandidateSwitchResult(
                    state=state,
                    action_attempt=action_attempt,
                    observation_attempt=observation_attempt,
                    confirmed_observation=observation,
                )
            if state in (
                CANDIDATE_SWITCH_OBSERVING,
                CANDIDATE_SWITCH_UNCHANGED,
            ):
                previous_ready_fingerprint = current_fingerprint
                previous_relation = relation
                continue

            previous_ready_fingerprint = None
            previous_relation = None
        stable_unchanged_after_full_budget = (
            state == CANDIDATE_SWITCH_UNCHANGED
            and all_observations_old
            and not saw_new
            and not saw_loading
            and not saw_unverifiable
            and not saw_capture_error
        )
        if stable_unchanged_after_full_budget:
            if not candidate_switch_focus_recovery_allowed(
                state,
                action_attempt,
            ):
                return CandidateSwitchResult(
                    state=CANDIDATE_SWITCH_FAILED,
                    action_attempt=action_attempt,
                    observation_attempt=(
                        CANDIDATE_SWITCH_MAX_OBSERVATIONS_PER_ACTION
                    ),
                    failure_reason="stable_unchanged_after_retry",
                )
            if stop_event:
                return None
            focus_error_type = None
            try:
                focus_recovered = restore_candidate_page_focus()
            except Exception as exc:
                focus_recovered = False
                focus_error_type = type(exc).__name__
            log_candidate_switch_event(
                "candidate_switch_focus_recovery",
                logging.WARNING,
                phase="post_next",
                state=state,
                action_attempt=action_attempt,
                observation_attempt=(
                    CANDIDATE_SWITCH_MAX_OBSERVATIONS_PER_ACTION
                ),
                old_fingerprint_count=len(previous_fingerprints),
                compare_relation=relation,
                r02_ready=load_ready,
                r02_reason=load_reason,
                failure_reason=(
                    None
                    if focus_recovered
                    else "focus_recovery_failed"
                ),
                event_stop_reason=stop_reason,
                candidate_in_batch=candidate_in_batch,
                total_viewed=total_viewed,
                error_type=focus_error_type,
            )
            if stop_event:
                return None
            if not focus_recovered:
                return CandidateSwitchResult(
                    state=CANDIDATE_SWITCH_FAILED,
                    action_attempt=action_attempt,
                    observation_attempt=(
                        CANDIDATE_SWITCH_MAX_OBSERVATIONS_PER_ACTION
                    ),
                    failure_reason="focus_recovery_failed",
                )
            log_candidate_switch_event(
                "candidate_switch_retry",
                logging.WARNING,
                phase="post_next",
                state=CANDIDATE_SWITCH_PENDING,
                action_attempt=action_attempt + 1,
                observation_attempt=0,
                old_fingerprint_count=len(previous_fingerprints),
                candidate_in_batch=candidate_in_batch,
                total_viewed=total_viewed,
            )
            continue

        return CandidateSwitchResult(
            state=CANDIDATE_SWITCH_FAILED,
            action_attempt=action_attempt,
            observation_attempt=CANDIDATE_SWITCH_MAX_OBSERVATIONS_PER_ACTION,
            failure_reason=(
                "comparison_unverifiable"
                if saw_unverifiable
                else "observation_budget_exhausted"
            ),
        )

    return CandidateSwitchResult(
        state=CANDIDATE_SWITCH_FAILED,
        action_attempt=action_attempt,
        observation_attempt=CANDIDATE_SWITCH_MAX_OBSERVATIONS_PER_ACTION,
        failure_reason="observation_budget_exhausted",
    )


def refresh_page(reason='已查看 100 位'):
    """按 F5 刷新页面"""
    if stop_event:
        return False
    logger.info(f'🔄 {reason}，按 F5 刷新页面')
    pyautogui.press('f5')
    return safe_wait(REFRESH_WAIT_SECONDS)


def recover_detail_page():
    """Refresh, reapply the calibrated filter, and reopen the first candidate."""
    if stop_event:
        return None, 'stopped'

    try:
        logger.info(
            'event=detail_load_recovery_step step=refresh decision=started'
        )
        refreshed = refresh_page(reason='详情页加载检测重试耗尽')
    except Exception as exc:
        if stop_event:
            return None, 'stopped'
        logger.error(
            'event=detail_load_recovery_step step=refresh '
            'decision=failed reason=refresh_failed error=%s',
            exc,
        )
        return False, 'refresh_failed'

    if not refreshed:
        if stop_event:
            return None, 'stopped'
        logger.error(
            'event=detail_load_recovery_step step=refresh '
            'decision=failed reason=refresh_failed'
        )
        return False, 'refresh_failed'

    logger.info(
        'event=detail_load_recovery_step step=refresh decision=completed'
    )
    try:
        logger.info(
            'event=detail_load_recovery_step step=batch_reopen decision=started'
        )
        reopened = apply_batch_filter_and_open_first_candidate()
    except Exception as exc:
        if stop_event:
            return None, 'stopped'
        logger.error(
            'event=detail_load_recovery_step step=batch_reopen '
            'decision=failed reason=batch_reopen_failed error=%s',
            exc,
        )
        return False, 'batch_reopen_failed'

    if not reopened:
        if stop_event:
            return None, 'stopped'
        logger.error(
            'event=detail_load_recovery_step step=batch_reopen '
            'decision=failed reason=batch_reopen_failed'
        )
        return False, 'batch_reopen_failed'

    logger.info(
        'event=detail_load_recovery_reopen_completed '
        'reason=reopen_completed next_action=retry_load_gate'
    )
    return True, 'reopen_completed'


# ─── 主循环 ─────────────────────────────────────────

def run():
    global stop_event, stop_reason, forward_consecutive, no_forward_mode, simple_mouse_enabled, action_mode
    global ocr_record_store, current_candidate_builder
    global candidate_record_sequence, recorded_observation_ids
    stop_event = False
    stop_reason = None
    simple_mouse_enabled = False
    action_mode = ACTION_MODE_FORWARD
    reset_focus_restore_calibration()
    reset_forward_click_calibration()
    reset_batch_filter_calibration()
    ocr_record_store = None
    current_candidate_builder = None
    candidate_record_sequence = 0
    recorded_observation_ids = {}

    # ── 交互/参数输入 ──
    try:
        cli_args = parse_args()
        no_forward_mode = cli_args['no_forward']
        simple_mouse_enabled = bool(cli_args.get('simple_mouse', False))
        get_user_input(
            keywords_str=cli_args['keywords'],
            email_str=cli_args['email'],
            duration_str=cli_args['duration_seconds'],
            auto=cli_args['auto'],
            no_forward=no_forward_mode,
            no_batch_filter=cli_args.get('no_batch_filter', False),
            action_mode_value=cli_args.get('action_mode'),
            calibration_profile_name=cli_args.get('calibration_profile', ''),
        )
    except ValueError as exc:
        print(f'[错误] {exc}')
        return 2

    initialize_run_ocr_storage()

    # 提前初始化并复用 OCR 引擎；校准仍延迟到第一位详情打开之后。
    if forward_enabled and forward_keywords:
        initialize_ocr()

    # ── 启动键盘监听（必须在交互输入之后，避免 exe 中 input() 冲突） ──
    try:
        listener.start()
    except Exception:
        close_run_ocr_storage(RunStatus.ERROR)
        raise

    logger.info('\n' + '=' * 50)
    logger.info('BOSS 直聘极简刷简历 v4 启动')
    logger.info(f'停留: {MIN_STAY_SECONDS}-{MAX_STAY_SECONDS}s | 每 {BATCH_SIZE} 人刷新')
    if forward_enabled:
        logger.info('rule_count=%s', len(forward_keywords))
        if no_forward_mode:
            logger.info('模式: 只执行 OCR 检测，真实邮件转发已禁用 (--no-forward)')
        else:
            logger.info(
                'alternate_email_provided=%s',
                str(bool(backup_email)).lower(),
            )
            logger.info(f'连续转发上限: {FORWARD_MAX_CONSEC}')
    else:
        logger.info('转发: 已禁用')
    logger.info('=' * 50)

    try:
        foreground_ready = bring_edge_foreground()
    except Exception:
        close_run_ocr_storage(RunStatus.ERROR)
        raise
    if not foreground_ready:
        close_run_ocr_storage(RunStatus.COMPLETED)
        return 0

    run_timer = None
    total_viewed = 0
    forward_consecutive = 0
    consecutive_load_recovery_count = 0
    previous_candidate_context = None
    run_exception_type = None

    try:
        if batch_filter_calibration_requested:
            ensure_batch_filter_regions_calibrated()

        if batch_filter_enabled:
            legacy_point = None
            if not open_first_candidate_for_batch():
                return 0
        else:
            logger.info(
                f'\n请将鼠标移到第一位候选人卡片上，'
                f'{COUNTDOWN_SECONDS} 秒后开始...'
            )
            if not safe_wait(COUNTDOWN_SECONDS):
                return 0

            click_x, click_y = pyautogui.position()
            logger.info(f'📍 固定点击位置: ({click_x}, {click_y})')
            legacy_point = (click_x, click_y)
            if not open_first_candidate_for_batch(legacy_point):
                return 0

        # 首位详情稳定后完成既有运行期校准；这些启动准备不计入运行时间。
        if focus_restore_calibration_requested:
            ensure_focus_restore_region_calibrated()
        if forward_click_calibration_requested:
            ensure_forward_click_regions_calibrated()
        if action_mode == ACTION_MODE_FAVORITE:
            if ensure_favorite_button_region_calibrated() is None:
                return 0
        if forward_enabled and forward_keywords:
            if not ensure_ocr_region_calibrated():
                return 0

        if stop_event:
            return 0

        run_timer = start_run_timer(run_duration_seconds)
        first_candidate_opened = True

        while not stop_event:
            restart_current_batch = False
            if not first_candidate_opened:
                previous_candidate_context = None
                if not open_first_candidate_for_batch(legacy_point):
                    break
            first_candidate_opened = False

            # 浏览本批次 100 位
            for i in range(BATCH_SIZE):
                if stop_event:
                    break

                start_candidate_ocr_recording(
                    candidate_in_batch=i + 1,
                    total_viewed=total_viewed,
                )

                if forward_enabled and forward_keywords:
                    if i == 0:
                        recovery_available = (
                            batch_filter_enabled
                            and batch_filter_regions is not None
                        )
                        (
                            load_outcome,
                            first_observation,
                            load_retry_number,
                            load_reason,
                        ) = run_detail_load_gate(
                            candidate_in_batch=i + 1,
                            total_viewed=total_viewed,
                            recovery_count=consecutive_load_recovery_count,
                            recovery_available=recovery_available,
                        )
                        if load_outcome == 'load_recovering':
                            previous_candidate_context = None
                            consecutive_load_recovery_count += 1
                            logger.warning(
                                'event=detail_load_recovery_start '
                                'candidate_in_batch=%s total_viewed=%s '
                                'retry_number=%s reason=%s '
                                'state=load_recovering recovery_count=%s '
                                'next_action=hard_refresh',
                                i + 1,
                                total_viewed,
                                load_retry_number,
                                load_reason,
                                consecutive_load_recovery_count,
                            )
                            recovery_success, _recovery_reason = (
                                recover_detail_page()
                            )
                            if recovery_success is not True:
                                if recovery_success is False:
                                    request_load_failed_stop(
                                        candidate_in_batch=i + 1,
                                        total_viewed=total_viewed,
                                        retry_number=load_retry_number,
                                        reason=_recovery_reason,
                                        recovery_count=(
                                            consecutive_load_recovery_count
                                        ),
                                    )
                                break
                            finalize_current_candidate_recording(
                                CaptureStatus.ABORTED,
                                None,
                                "load_recovery_restart",
                            )
                            first_candidate_opened = True
                            restart_current_batch = True
                            break
                        if load_outcome != 'loaded':
                            if load_outcome == 'retries_exhausted':
                                if not recovery_available:
                                    load_reason = (
                                        'hard_recovery_unavailable'
                                    )
                                else:
                                    load_reason = (
                                        'max_consecutive_load_recoveries_reached'
                                    )
                                request_load_failed_stop(
                                    candidate_in_batch=i + 1,
                                    total_viewed=total_viewed,
                                    retry_number=load_retry_number,
                                    reason=load_reason,
                                    recovery_count=(
                                        consecutive_load_recovery_count
                                    ),
                                )
                            break
                    else:
                        if previous_candidate_context is None:
                            request_candidate_switch_failed_stop(
                                CandidateSwitchResult(
                                    state=CANDIDATE_SWITCH_FAILED,
                                    action_attempt=0,
                                    observation_attempt=0,
                                    failure_reason=(
                                        'formal_fingerprint_invariant_failed'
                                    ),
                                ),
                                candidate_in_batch=i + 1,
                                total_viewed=total_viewed,
                            )
                            break
                        switch_result = confirm_candidate_switch(
                            previous_candidate_context,
                            candidate_in_batch=i + 1,
                            total_viewed=total_viewed,
                        )
                        previous_candidate_context = None
                        if switch_result is None:
                            break
                        if (
                            not candidate_switch_scan_allowed(
                                switch_result.state
                            )
                            or switch_result.confirmed_observation is None
                        ):
                            if switch_result.state != CANDIDATE_SWITCH_FAILED:
                                switch_result = CandidateSwitchResult(
                                    state=CANDIDATE_SWITCH_FAILED,
                                    action_attempt=(
                                        switch_result.action_attempt
                                    ),
                                    observation_attempt=(
                                        switch_result.observation_attempt
                                    ),
                                    failure_reason=(
                                        'comparison_unverifiable'
                                    ),
                                )
                            request_candidate_switch_failed_stop(
                                switch_result,
                                candidate_in_batch=i + 1,
                                total_viewed=total_viewed,
                            )
                            break
                        first_observation = (
                            switch_result.confirmed_observation
                        )

                    total_viewed += 1
                    if i == 0:
                        logger.info(
                            'event=detail_load_check candidate_in_batch=%s '
                            'total_viewed=%s attempt=%s retry_number=%s '
                            'ocr_box_count=%s ocr_text_length=%s '
                            'decision=ready reason=%s state=loaded '
                            'recovery_count=%s '
                            'next_action=reuse_first_scan',
                            i + 1,
                            total_viewed,
                            (
                                'initial'
                                if load_retry_number == 0
                                else 'retry'
                            ),
                            load_retry_number,
                            first_observation.ocr_box_count,
                            first_observation.ocr_text_length,
                            load_reason,
                            consecutive_load_recovery_count,
                        )
                    if i == 0 and consecutive_load_recovery_count > 0:
                        logger.info(
                            'event=detail_load_recovery_confirmed '
                            'candidate_in_batch=%s total_viewed=%s '
                            'attempt=%s retry_number=%s ocr_box_count=%s '
                            'ocr_text_length=%s decision=ready reason=%s '
                            'state=loaded recovery_count=%s '
                            'next_action=reuse_first_scan',
                            i + 1,
                            total_viewed,
                            (
                                'initial'
                                if load_retry_number == 0
                                else 'retry'
                            ),
                            load_retry_number,
                            first_observation.ocr_box_count,
                            first_observation.ocr_text_length,
                            load_reason,
                            consecutive_load_recovery_count,
                        )
                        consecutive_load_recovery_count = 0
                    view_completed, detection_result = view_candidate(
                        i,
                        first_observation=first_observation,
                    )
                    if not view_completed:
                        finalize_active_candidate_for_stop(
                            detection_result=detection_result,
                        )
                        break

                    capture_status, capture_end_reason = (
                        candidate_capture_status(detection_result)
                    )
                    if i < BATCH_SIZE - 1:
                        (
                            previous_candidate_context,
                            context_reason,
                        ) = prepare_candidate_switch_context(
                            detection_result,
                            candidate_in_batch=i + 1,
                            total_viewed=total_viewed,
                        )
                        finalize_current_candidate_recording(
                            capture_status,
                            capture_end_reason,
                            detection_result=detection_result,
                        )
                        if previous_candidate_context is None:
                            if context_reason != 'stopped':
                                request_candidate_switch_failed_stop(
                                    CandidateSwitchResult(
                                        state=CANDIDATE_SWITCH_FAILED,
                                        action_attempt=0,
                                        observation_attempt=1,
                                        failure_reason=(
                                            context_reason
                                            or 'pre_switch_baseline_unavailable'
                                        ),
                                    ),
                                    candidate_in_batch=i + 1,
                                    total_viewed=total_viewed,
                                )
                            break
                    else:
                        finalize_current_candidate_recording(
                            capture_status,
                            capture_end_reason,
                            detection_result=detection_result,
                        )
                else:
                    total_viewed += 1
                    view_completed, _detection_result = view_candidate(i)
                    if not view_completed:
                        finalize_active_candidate_for_stop()
                        break
                    finalize_current_candidate_recording(
                        CaptureStatus.COMPLETED,
                        "existing_flow_completed",
                    )
                    if i < BATCH_SIZE - 1:
                        if not next_candidate():
                            break

            if stop_event:
                break
            if restart_current_batch:
                previous_candidate_context = None
                continue

            # 每 100 位刷新
            previous_candidate_context = None
            forward_consecutive = 0  # 刷新后重置连续计数
            if not refresh_page():
                break

            logger.info(f'📊 累计已查看: {total_viewed} 位')

    except Exception as e:
        run_exception_type = type(e).__name__
        logger.error('运行异常 error_type=%s', run_exception_type)
    finally:
        previous_candidate_context = None
        finalize_active_candidate_for_stop(run_exception_type)
        if run_timer is not None:
            run_timer.cancel()
        if run_exception_type is not None:
            run_status = RunStatus.ERROR
        elif stop_reason in ("esc", "run_duration_elapsed") or (
            stop_event and stop_reason is None
        ):
            run_status = RunStatus.INTERRUPTED
        elif stop_reason is not None:
            run_status = RunStatus.ERROR
        else:
            run_status = RunStatus.COMPLETED
        close_run_ocr_storage(run_status)
        logger.info(f'\n🏁 停止运行。累计查看 {total_viewed} 位候选人。')
        logger.info(f'event=run_stopped stop_reason={stop_reason or "none"}')
        logger.info(f'日志文件: logs/simple_brush.log\n')
    return 0


def main():
    """Dispatch the interactive startup menu without changing CLI run behavior."""
    try:
        cli_args = parse_args()
    except ValueError as exc:
        print(f'[错误] {exc}')
        return 2

    if is_noninteractive_startup(cli_args):
        return run()

    while True:
        action = choose_startup_action()
        if action == 'run':
            return run()
        if action == 'exit':
            return 0
        launch_calibration_template()


if __name__ == '__main__':
    file_log_handler = configure_file_logging()
    exit_code = 0
    try:
        exit_code = main() or 0
    except KeyboardInterrupt:
        pass
    finally:
        stop_event = True
        try:
            listener.stop()
        finally:
            close_file_logging(file_log_handler)
    if exit_code:
        sys.exit(exit_code)
