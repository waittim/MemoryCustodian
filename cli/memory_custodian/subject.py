"""Preview-first Subject registry commands."""

from __future__ import annotations

import hashlib
from pathlib import Path

from .entries import parse_structured_entries, validate_evidence
from .locking import (
    create_private_file,
    discard_private_file,
    project_mutation_guard,
    read_private_file,
)
from .mutations import TextMutation, apply_mutations
from .plans import (
    MutationPlan,
    digest_path,
    pending_plan_directory,
    print_plan,
)
from .protocol import (
    CURRENT_PROTOCOL_VERSION,
    compare_versions,
    prepended_text,
    project_id_from_manifest,
    protocol_metadata,
    resolve_memory_dir,
    resolve_project_root,
)
from .subjects import (
    SUBJECT_ID_RE,
    Subject,
    generate_subject_id,
    load_subjects,
    normalize_alias,
    normalize_canonical_ref,
    render_subject,
    subject_indexes,
    validate_subject_kind,
)


def _registry(memory_dir: Path) -> Path:
    path = memory_dir / "subjects.md"
    if not path.exists():
        raise ValueError("subjects.md is missing; run `memory-custodian migrate` or `init --repair`.")
    return path


def _project(args) -> tuple[Path, Path, str]:
    project_root = resolve_project_root(args.project_root)
    memory_dir = resolve_memory_dir(project_root, args.memory_dir)
    manifest = memory_dir / "manifest.md"
    if not manifest.exists():
        raise ValueError("manifest.md is missing; Subject operations require Protocol 0.7 metadata.")
    metadata = protocol_metadata(manifest.read_text(encoding="utf-8"))
    comparison = compare_versions(
        metadata.get("protocol_version", "0.5"),
        CURRENT_PROTOCOL_VERSION,
    )
    if comparison is None:
        raise ValueError("Project manifest has an invalid protocol version.")
    if comparison != 0:
        raise ValueError("Subject operations require Protocol 0.7.")
    if metadata.get("subject_schema_version") != "1":
        raise ValueError("Subject schema is not initialized; run `memory-custodian migrate`.")
    return project_root, memory_dir, project_id_from_manifest(manifest.read_text(encoding="utf-8"))


def _find(subjects: list[Subject], subject_id: str) -> Subject:
    matches = [item for item in subjects if item.subject_id.casefold() == subject_id.casefold()]
    if not matches:
        raise ValueError(f"Subject ID not found: {subject_id}")
    if len(matches) > 1:
        raise ValueError(f"Duplicate Subject ID prevents mutation: {subject_id}")
    return matches[0]


def _pending_subject_id(project_id: str, registry: Path, normalized_args: str) -> tuple[str, Path]:
    fingerprint = hashlib.sha256(
        f"{project_id}\0{digest_path(registry)}\0{normalized_args}".encode("utf-8")
    ).hexdigest()[:32]
    path = pending_plan_directory() / f"subject-{fingerprint}.id"
    generated = generate_subject_id()
    create_private_file(path, generated + "\n")
    value = read_private_file(path).strip()
    if not SUBJECT_ID_RE.fullmatch(value):
        raise ValueError(f"Invalid pending Subject ID seed: {path}")
    return value, path


def _replace_subject(text: str, subject: Subject, replacement: str) -> str:
    if subject.text not in text:
        raise ValueError(f"Subject changed while building mutation: {subject.subject_id}")
    return text.replace(subject.text, replacement.strip(), 1).rstrip() + "\n"


def _print_preflight(
    subjects: list[Subject], aliases: tuple[str, ...], canonical_ref: str | None
) -> None:
    active = [item for item in subjects if item.status == "active"]
    print("Active subjects:")
    if active:
        for item in active:
            print(f"- {item.subject_id}: {item.title}")
    else:
        print("- none")
    _by_id, by_alias, by_ref = subject_indexes(subjects)
    exact: dict[str, Subject] = {}
    for alias in aliases:
        if normalize_alias(alias) in by_alias:
            owner = by_alias[normalize_alias(alias)]
            exact[owner.subject_id] = owner
    if canonical_ref and canonical_ref in by_ref:
        owner = by_ref[canonical_ref]
        exact[owner.subject_id] = owner
    print("Exact alias/canonical-ref matches:")
    if exact:
        for item in exact.values():
            print(f"- {item.subject_id}: {item.title}")
    else:
        print("- none")


def _apply_preview(
    args,
    project_root: Path,
    manifest_path: Path,
    project_id: str,
    build,
    *,
    seed_path: Path | None = None,
) -> int:
    plan = build()
    if not plan.mutations:
        print("No Subject registry changes required.")
        return 0
    print_plan(plan)
    if not args.apply:
        print("Dry run only. Re-run with --apply --confirm-plan <PLAN_ID>.")
        return 0
    if not args.confirm_plan:
        raise ValueError("Subject registry apply requires --confirm-plan <PLAN_ID>.")
    with project_mutation_guard(
        project_root,
        manifest_path,
        f"subject {args.subject_command}",
        timeout=args.lock_timeout,
        break_stale=args.break_stale_lock,
    ) as guard:
        if guard.project_id != project_id:
            raise ValueError(
                "Project identity changed before Subject mutation apply; preview again."
            )
        if (
            compare_versions(
                protocol_metadata(guard.manifest_text or "").get(
                    "protocol_version",
                    "0.5",
                ),
                CURRENT_PROTOCOL_VERSION,
            )
            != 0
        ):
            raise ValueError(
                "Subject mutation requires Protocol 0.7; project protocol changed "
                "before apply."
            )
        current = build()
        if current.plan_id != args.confirm_plan:
            print_plan(current)
            raise ValueError(
                f"Stale or mismatched plan: confirmed {args.confirm_plan}, "
                f"current Plan ID is {current.plan_id}. No files written."
            )
        completed = apply_mutations(list(current.mutations))
    if seed_path:
        discard_private_file(seed_path)
    print("Applied Subject registry plan. Written files:")
    for path in completed:
        print(f"- {path}")
    return 0


def _list(args) -> int:
    _project_root, memory_dir, _project_id = _project(args)
    subjects = [item for item in load_subjects(memory_dir) if item.status == "active"]
    print("Active subjects:")
    if not subjects:
        print("- none")
    for item in subjects:
        suffix = f" [{item.canonical_ref}]" if item.canonical_ref else ""
        print(f"- {item.subject_id}: {item.title} ({item.kind}){suffix}")
    return 0


def _show(args) -> int:
    _project_root, memory_dir, _project_id = _project(args)
    subject = _find(load_subjects(memory_dir), args.subject_id)
    print(f"Subject ID: {subject.subject_id}")
    print(f"Title: {subject.title}")
    print(f"Status: {subject.status}")
    print(f"Kind: {subject.kind}")
    print(f"Canonical-Ref: {subject.canonical_ref or 'none'}")
    print("Aliases:")
    for alias in subject.aliases:
        print(f"- {alias}")
    if not subject.aliases:
        print("- none")
    print("Evidence:")
    for item in subject.evidence:
        print(f"- {item}")
    print("Referenced by:")
    references = []
    for path in memory_dir.rglob("*.md"):
        if path.name == "subjects.md":
            continue
        for entry in parse_structured_entries(path, path.read_text(encoding="utf-8")):
            if any(
                entry.fields.get(field, "").casefold() == subject.subject_id.casefold()
                for field in ("Subject", "Provisional-Subject")
            ):
                references.append((entry.entry_id, path.relative_to(memory_dir).as_posix()))
    if references:
        for entry_id, relative in references:
            print(f"- {entry_id}: {relative}")
    else:
        print("- none")
    return 0


def _add(args) -> int:
    project_root, memory_dir, project_id = _project(args)
    registry = _registry(memory_dir)
    kind = validate_subject_kind(args.kind)
    canonical_ref = normalize_canonical_ref(args.canonical_ref) if args.canonical_ref else None
    aliases = tuple(dict.fromkeys(
        alias.strip() for alias in [args.title, *args.alias] if alias.strip()
    ))
    evidence = validate_evidence(args.evidence, project_root)
    subjects = load_subjects(memory_dir)
    _print_preflight(subjects, aliases, canonical_ref)
    _by_id, by_alias, by_ref = subject_indexes(subjects)
    collisions = {
        by_alias[normalize_alias(alias)].subject_id
        for alias in aliases
        if normalize_alias(alias) in by_alias
    }
    if canonical_ref and canonical_ref in by_ref:
        collisions.add(by_ref[canonical_ref].subject_id)
    if collisions:
        raise ValueError(
            "Exact Subject identity collision; use the existing Subject: " + ", ".join(sorted(collisions))
        )
    normalized_args = "\0".join([args.title, kind, canonical_ref or "", *aliases, *evidence])
    subject_id, seed_path = _pending_subject_id(project_id, registry, normalized_args)

    def build() -> MutationPlan:
        current_subjects = load_subjects(memory_dir)
        _current_by_id, current_aliases, current_refs = subject_indexes(current_subjects)
        for alias in aliases:
            owner = current_aliases.get(normalize_alias(alias))
            if owner:
                raise ValueError(f"Exact alias collision with {owner.subject_id}: {alias!r}")
        if canonical_ref and canonical_ref in current_refs:
            raise ValueError(
                f"Exact Canonical-Ref collision with {current_refs[canonical_ref].subject_id}: {canonical_ref}"
            )
        entry = render_subject(subject_id, args.title, kind, canonical_ref, aliases, evidence)
        updated = prepended_text(registry.read_text(encoding="utf-8"), entry)
        return MutationPlan(
            "subject add",
            {
                "title": " ".join(args.title.split()),
                "kind": kind,
                "canonical_ref": canonical_ref,
                "aliases": list(aliases),
                "evidence": list(evidence),
            },
            project_id,
            CURRENT_PROTOCOL_VERSION,
            (TextMutation(registry, updated),),
            project_root=project_root,
        )

    return _apply_preview(
        args,
        project_root,
        memory_dir / "manifest.md",
        project_id,
        build,
        seed_path=seed_path,
    )


def _rename(args) -> int:
    project_root, memory_dir, project_id = _project(args)
    registry = _registry(memory_dir)
    new_title = " ".join(args.title.split())
    if not new_title:
        raise ValueError("Subject title must not be empty.")

    def build() -> MutationPlan:
        subjects = load_subjects(memory_dir)
        subject = _find(subjects, args.subject_id)
        _by_id, by_alias, _by_ref = subject_indexes(subjects)
        owner = by_alias.get(normalize_alias(new_title))
        if owner and owner.subject_id.casefold() != subject.subject_id.casefold():
            raise ValueError(f"Exact alias collision with {owner.subject_id}: {new_title!r}")
        updated_entry = render_subject(
            subject.subject_id,
            new_title,
            subject.kind,
            subject.canonical_ref,
            subject.aliases,
            subject.evidence,
        )
        updated = _replace_subject(registry.read_text(encoding="utf-8"), subject, updated_entry)
        mutations = () if updated == registry.read_text(encoding="utf-8") else (TextMutation(registry, updated),)
        return MutationPlan(
            "subject rename",
            {"subject_id": subject.subject_id, "title": new_title},
            project_id,
            CURRENT_PROTOCOL_VERSION,
            mutations,
            project_root=project_root,
        )

    return _apply_preview(
        args,
        project_root,
        memory_dir / "manifest.md",
        project_id,
        build,
    )


def _add_alias(args) -> int:
    project_root, memory_dir, project_id = _project(args)
    registry = _registry(memory_dir)
    alias = " ".join(args.alias_value.split())
    if not alias:
        raise ValueError("Alias must not be empty.")

    def build() -> MutationPlan:
        subjects = load_subjects(memory_dir)
        subject = _find(subjects, args.subject_id)
        _by_id, by_alias, _by_ref = subject_indexes(subjects)
        owner = by_alias.get(normalize_alias(alias))
        if owner and owner.subject_id.casefold() != subject.subject_id.casefold():
            raise ValueError(f"Exact alias collision with {owner.subject_id}: {alias!r}")
        aliases = tuple(dict.fromkeys([*subject.aliases, alias]))
        updated_entry = render_subject(
            subject.subject_id,
            subject.title,
            subject.kind,
            subject.canonical_ref,
            aliases,
            subject.evidence,
        )
        original = registry.read_text(encoding="utf-8")
        updated = _replace_subject(original, subject, updated_entry)
        mutations = () if updated == original else (TextMutation(registry, updated),)
        return MutationPlan(
            "subject add-alias",
            {"subject_id": subject.subject_id, "alias": alias},
            project_id,
            CURRENT_PROTOCOL_VERSION,
            mutations,
            project_root=project_root,
        )

    return _apply_preview(
        args,
        project_root,
        memory_dir / "manifest.md",
        project_id,
        build,
    )


def _merge(args) -> int:
    """Inventory and preview only; Protocol 0.8 supplies the transaction journal."""

    from .conflicts import canonical_entries

    _project_root, memory_dir, project_id = _project(args)
    subjects = load_subjects(memory_dir)
    source = _find(subjects, args.subject_id)
    target = _find(subjects, args.target_subject_id)
    if source.subject_id.casefold() == target.subject_id.casefold():
        raise ValueError("Subject merge source and target must be different.")
    current: list[str] = []
    historical: list[str] = []
    resulting: dict[tuple[str, str], list[str]] = {}
    for entry in canonical_entries(memory_dir, include_archive=True):
        reference = entry.fields.get("Subject") or entry.fields.get("Provisional-Subject")
        if not reference or reference.casefold() != source.subject_id.casefold():
            continue
        relative = entry.path.relative_to(memory_dir).as_posix()
        item = f"{entry.entry_id} ({relative}; {entry.status})"
        if entry.status in {"active", "candidate"} and not relative.startswith("archive/"):
            current.append(item)
            if entry.status == "active":
                resulting.setdefault((entry.scope, entry.fields.get("Facet", "")), []).append(entry.entry_id)
        else:
            historical.append(item)
    for entry in canonical_entries(memory_dir):
        if entry.status == "active" and entry.fields.get("Subject", "").casefold() == target.subject_id.casefold():
            resulting.setdefault((entry.scope, entry.fields.get("Facet", "")), []).append(entry.entry_id)
    blockers = [
        f"Resulting structural identity {scope}+{target.subject_id}+{facet} has owners: {', '.join(ids)}"
        for (scope, facet), ids in sorted(resulting.items()) if len(ids) > 1
    ]
    reviews: list[str] = []
    if source.canonical_ref and target.canonical_ref and source.canonical_ref != target.canonical_ref:
        reviews.append("Source and target have different Canonical-Ref values; reviewer must choose target identity.")
    source_aliases = {source.title.casefold(), *(item.casefold() for item in source.aliases)}
    target_aliases = {target.title.casefold(), *(item.casefold() for item in target.aliases)}
    if source_aliases & target_aliases:
        reviews.append("Source and target share an exact normalized alias.")
    seed = (
        f"subject-merge\0{project_id}\0{source.subject_id}\0{target.subject_id}\0"
        + "\0".join(sorted(current + historical + blockers))
    ).encode("utf-8")
    print("Subject merge preview:")
    print(f"Source: {source.subject_id} — {source.title}")
    print(f"Target: {target.subject_id} — {target.title}")
    print("Source registry unit:")
    print(source.text.strip())
    print("Target registry unit:")
    print(target.text.strip())
    print("Current references planned for future mutation:")
    for item in sorted(current) or ["none"]:
        print(f"- {item}")
    print("Historical references retained without mechanical rewrite:")
    for item in sorted(historical) or ["none"]:
        print(f"- {item}")
    print("Alias/Canonical-Ref review:")
    for item in reviews or ["none"]:
        print(f"- {item}")
    print("Required reconciliation/blockers:")
    if current:
        print(
            f"- Future subject-merged reconciliation must cover current references: "
            f"{', '.join(sorted(item.split(' ', 1)[0] for item in current))}"
        )
    for item in blockers or ([] if current else ["none"]):
        print(f"- {item}")
    print(f"Plan ID: {hashlib.sha256(seed).hexdigest()[:16]}")
    print("Future semantics: current active/candidate references mutate; source gains Merged-Into; historical entries retain their original Subject ID.")
    print("Transactional Subject merge apply requires Protocol 0.8.")
    return 0


def run(args) -> int:
    handlers = {
        "list": _list,
        "show": _show,
        "add": _add,
        "rename": _rename,
        "add-alias": _add_alias,
        "merge": _merge,
    }
    return handlers[args.subject_command](args)
