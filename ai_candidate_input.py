from dataclasses import dataclass

from ocr_records import CandidateOcrDocument


@dataclass(frozen=True)
class AICandidateInput:
    candidate_record_id: str
    resume_text: str

    def __post_init__(self) -> None:
        if not isinstance(self.candidate_record_id, str):
            raise ValueError("candidate_record_id must be a string")
        if (
            not isinstance(self.resume_text, str)
            or not self.resume_text.strip()
        ):
            raise ValueError("resume_text must contain non-whitespace text")


def build_ai_candidate_input(
    candidate: CandidateOcrDocument,
) -> AICandidateInput:
    if not isinstance(candidate, CandidateOcrDocument):
        raise TypeError("candidate must be a CandidateOcrDocument")
    return AICandidateInput(
        candidate_record_id=candidate.candidate_record_id,
        resume_text=candidate.document_text,
    )
