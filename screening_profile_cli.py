"""Interactive Configuration Mode CLI for ScreeningProfile Drafts."""

from screening_profile import (
    ScreeningProfileDraft,
    ScreeningProfileIOError,
    ScreeningProfileStore,
    ScreeningProfileValidationError,
)


def _show_draft(draft: ScreeningProfileDraft | None) -> None:
    if draft is None:
        print("No current Draft. Create a Profile or edit an existing Profile first.")
        return

    base = (
        "new Profile"
        if draft.base_profile_version is None
        else "latest v{0}".format(draft.base_profile_version)
    )
    print("\nCurrent ScreeningProfile Draft")
    print("Profile ID: {0}".format(draft.screening_profile_id))
    print("Base: {0}".format(base))
    if not draft.criteria:
        print("Criteria: none")
        return
    print("Criteria:")
    for criterion in draft.criteria:
        print(
            "  {0}: {1} [{2}]".format(
                criterion.criterion_id,
                criterion.criterion_text,
                criterion.rule,
            )
        )


def _list_profiles(store: ScreeningProfileStore) -> None:
    profile_ids = store.list_profile_ids()
    if not profile_ids:
        print("No saved ScreeningProfiles.")
        return

    print("\nSaved ScreeningProfiles:")
    for screening_profile_id in profile_ids:
        latest = store.load_latest(screening_profile_id)
        print(
            "  {0}: latest v{1}".format(
                screening_profile_id,
                latest.profile_version,
            )
        )


def _draft_required(draft: ScreeningProfileDraft | None) -> bool:
    if draft is not None:
        return True
    print("No current Draft. Create a Profile or edit an existing Profile first.")
    return False


def _another_draft_is_in_progress() -> None:
    print(
        "A Draft is already in progress. Continue it, save it, or return before "
        "creating or editing another Profile."
    )


def run_screening_profile_configuration(
    store: ScreeningProfileStore | None = None,
) -> str | None:
    """Run Configuration Mode until a Profile is prepared or Human returns."""

    if store is None:
        store = ScreeningProfileStore()
    draft: ScreeningProfileDraft | None = None

    while True:
        print("\nScreeningProfile Configuration")
        print("1. List Profile IDs and latest version numbers")
        print("2. Create new Profile Draft")
        print("3. Edit existing Profile by ID")
        print("4. Add Criterion")
        print("5. Edit criterion_text")
        print("6. Delete Criterion")
        print("7. Show current Draft")
        print("8. Human Save")
        print("9. Prepare Profile by ID for next Run")
        print("0. Return")
        choice = input("Select action: ").strip()

        if choice == "0":
            return None
        if choice == "1":
            try:
                _list_profiles(store)
            except (ScreeningProfileValidationError, ScreeningProfileIOError) as exc:
                print("Cannot list Profiles: {0}".format(exc))
        elif choice == "2":
            if draft is not None:
                _another_draft_is_in_progress()
                continue
            draft = store.create_draft()
            print("Created new Profile Draft: {0}".format(draft.screening_profile_id))
        elif choice == "3":
            if draft is not None:
                _another_draft_is_in_progress()
                continue
            screening_profile_id = input("Profile ID to edit: ").strip()
            try:
                draft = store.create_draft_from_latest(screening_profile_id)
            except (ScreeningProfileValidationError, ScreeningProfileIOError) as exc:
                print("Cannot edit Profile: {0}".format(exc))
            else:
                print(
                    "Editing latest v{0} of Profile {1}.".format(
                        draft.base_profile_version,
                        draft.screening_profile_id,
                    )
                )
        elif choice == "4":
            if not _draft_required(draft):
                continue
            criterion_text = input("Criterion text: ")
            try:
                criterion = store.add_criterion(draft, criterion_text)
            except (ScreeningProfileValidationError, ScreeningProfileIOError) as exc:
                print("Cannot add Criterion: {0}".format(exc))
            else:
                print("Added Criterion {0}.".format(criterion.criterion_id))
        elif choice == "5":
            if not _draft_required(draft):
                continue
            criterion_id = input("Criterion ID to edit: ").strip()
            criterion_text = input("New criterion_text: ")
            try:
                criterion = store.edit_criterion(
                    draft,
                    criterion_id,
                    criterion_text,
                )
            except (ScreeningProfileValidationError, ScreeningProfileIOError) as exc:
                print("Cannot edit Criterion: {0}".format(exc))
            else:
                print("Updated Criterion {0}.".format(criterion.criterion_id))
        elif choice == "6":
            if not _draft_required(draft):
                continue
            criterion_id = input("Criterion ID to delete: ").strip()
            try:
                store.delete_criterion(draft, criterion_id)
            except (ScreeningProfileValidationError, ScreeningProfileIOError) as exc:
                print("Cannot delete Criterion: {0}".format(exc))
            else:
                print("Deleted Criterion {0}.".format(criterion_id))
        elif choice == "7":
            _show_draft(draft)
        elif choice == "8":
            if not _draft_required(draft):
                continue
            try:
                version = store.save_draft(draft)
            except (ScreeningProfileValidationError, ScreeningProfileIOError) as exc:
                print("Cannot save Draft: {0}".format(exc))
            else:
                if version is None:
                    print("No content changes; no new Version was created.")
                else:
                    print(
                        "Saved Profile {0} v{1} ({2}).".format(
                            version.screening_profile_id,
                            version.profile_version,
                            version.criteria_digest,
                        )
                    )
                    draft = None
        elif choice == "9":
            screening_profile_id = input("Profile ID to prepare: ").strip()
            try:
                store.load_latest(screening_profile_id)
            except (ScreeningProfileValidationError, ScreeningProfileIOError) as exc:
                print("Cannot prepare Profile: {0}".format(exc))
            else:
                print(
                    "Prepared Profile {0} for the next Run.".format(
                        screening_profile_id
                    )
                )
                return screening_profile_id
        else:
            print("Invalid action.")
