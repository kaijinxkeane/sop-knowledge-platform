"""Admin command line (run inside the api container or from backend/).

    python -m app.cli sync-config [--reset-roles]   spaces + default roles from config/
    python -m app.cli create-admin EMAIL "NAME"     first admin; prints a one-time invite token
    python -m app.cli accept-invite TOKEN           set a password for an invite (prompts)
    python -m app.cli index [--full] [--no-embed]   (re)index the vault now
    python -m app.cli classify [--limit N]          run the Classifier on pending notes
    python -m app.cli train-sorter                  train the sorter from filed documents now
    python -m app.cli eval-classifier [--model TAG] Phase 2b eval on demo-vault/ (local model)
    python -m app.cli eval-answers [--model TAG]    Phase 3 answering eval (dev stack, demo vault)
    python -m app.cli compare-evals A.json B.json   paired comparison of two eval runs (--out)
    python -m app.cli eval-retrieval [--questions F] do the passages contain the answer?
    python -m app.cli eval-conflicts [--stage judge|search] [--set dev|holdout]
                                                    conflict-check eval (local, no DB)

Development only (refused unless SOP_ENV=development; fictional data):
    python -m app.cli seed-demo                     demo users + demo document labels
    python -m app.cli totp-code EMAIL               current two-factor code for a demo user
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import getpass
import hashlib
import sys
from datetime import UTC, datetime
from pathlib import Path

import pyotp
from sqlalchemy import select

from app.config import get_settings
from app.db.session import get_engine, get_sessionmaker
from app.demo import DEMO_PASSWORD, DEMO_USERS
from app.identity import create_user, get_user_by_email, sync_roles, sync_spaces
from app.security import passwords, totp
from app.security.tokens import hash_opaque


def _demo_totp_secret(email: str) -> str:
    return base64.b32encode(hashlib.sha256(f"demo-totp:{email}".encode()).digest()[:20]).decode()


def _require_dev() -> None:
    if get_settings().environment != "development":
        sys.exit("refused: demo commands only run with SOP_ENV=development")


async def cmd_sync_config(reset_roles: bool) -> None:
    async with get_sessionmaker()() as s:
        spaces = await sync_spaces(s)
        roles = await sync_roles(s, reset=reset_roles)
        await s.commit()
    print(f"spaces updated: {spaces or 'none'}; roles created: {roles or 'none'}")


async def cmd_create_admin(email: str, name: str) -> None:
    async with get_sessionmaker()() as s:
        await sync_spaces(s)
        await sync_roles(s)
        user, token = await create_user(
            s,
            email=email,
            display_name=name,
            role_names=["employee", "platform-admin"],
            home_space=None,
            actor_id=None,
        )
        await s.commit()
    print(f"created admin {user.email}")
    print("one-time invite token (set the password with `accept-invite`; then sign in and")
    print(f"set up two-factor):\n\n  {token}\n")


async def cmd_accept_invite(token: str) -> None:
    from app.db.models import OneTimeToken

    password = getpass.getpass("new password: ")
    if password != getpass.getpass("repeat: "):
        sys.exit("passwords differ")
    async with get_sessionmaker()() as s:
        row = (
            await s.execute(
                select(OneTimeToken).where(OneTimeToken.token_hash == hash_opaque(token))
            )
        ).scalar_one_or_none()
        if row is None or row.used_at or row.expires_at <= datetime.now(UTC):
            sys.exit("invalid or expired invite")
        from app.db.models import User

        user = await s.get(User, row.user_id)
        try:
            user.password_hash = passwords.hash_password(password)
        except passwords.PasswordPolicyError as exc:
            sys.exit(str(exc))
        row.used_at = datetime.now(UTC)
        await s.commit()
    print("password set; sign in to set up two-factor")


async def cmd_index(full: bool, no_embed: bool) -> None:
    from app.retrieval.embed import embed_documents
    from app.vault.git import GitVault
    from app.vault.indexer import Indexer

    git = GitVault(get_settings().vault_path)
    if not git.is_repo():
        sys.exit(f"vault is not a git repository: {git.root}")
    async with get_sessionmaker()() as s:
        await sync_spaces(s)
        await s.commit()
    indexer = Indexer(git, get_sessionmaker(), None if no_embed else embed_documents)
    from app.vault.help import sync_with_help

    print(await sync_with_help(indexer, full=full))


async def cmd_classify(limit: int, model: str | None = None) -> None:
    import dataclasses

    from app.classify.model import gateway_classifier
    from app.classify.service import ClassifierService
    from app.models.gateway import build_gateway
    from app.spaces import space_profiles

    gateway = build_gateway()
    if model:
        gateway.config.tiers["classifier"] = dataclasses.replace(
            gateway.config.tier("classifier"), model=model
        )
    service = ClassifierService(get_sessionmaker(), gateway_classifier(gateway, space_profiles()))
    total = {}
    while True:
        report = (await service.run_pending(limit=limit)).summary()
        for k, v in report.items():
            total[k] = total.get(k, 0) + v
        if not report["classified"]:
            break
    print(total)


async def cmd_eval_classifier(
    model: str | None,
    tier: str,
    repeats: int,
    blind: bool,
    out: str | None,
    example_pool: int | None = None,
    sorter: bool = False,
    cases: str = "dev",
) -> None:
    import dataclasses
    import json

    from app.classify.evaluate import evaluate, load_items
    from app.classify.model import gateway_classifier
    from app.config import REPO_ROOT
    from app.models.gateway import build_gateway
    from app.retrieval.embed import embed_documents
    from app.spaces import space_profiles

    gateway = build_gateway()
    if model:
        cfg = gateway.config.tier(tier)
        gateway.config.tiers[tier] = dataclasses.replace(cfg, model=model)
    used = gateway.config.tier(tier)
    if used.location != "local":
        sys.exit("the classifier eval runs on local tiers only")
    spaces = space_profiles()
    eval_dir = get_settings().config_dir / "eval"
    items = load_items(
        REPO_ROOT / "demo-vault",
        REPO_ROOT / "demo-vault-labels.yaml",
        eval_dir / "classifier-cases.yaml",
    )
    train_items = None
    if cases == "holdout":
        # Test on the held-out notes; everything else plays "already filed by people".
        train_items, items = (
            items,
            [
                i
                for i in load_items(
                    REPO_ROOT / "demo-vault",
                    REPO_ROOT / "demo-vault-labels.yaml",
                    eval_dir / "classifier-holdout.yaml",
                )
                if i.source == "case"
            ],
        )
        if example_pool:
            example_pool = len(train_items)

    def progress(t):
        if t.outcome != "exact":
            print(
                f"  run {t.run + 1} {t.outcome:15} {t.item}: got {t.got}, want {t.want}", flush=True
            )

    result = await evaluate(
        gateway_classifier(gateway, spaces, tier),
        items,
        model=used.model,
        known_spaces=set(spaces),
        repeats=repeats,
        blind=blind,
        progress=progress,
        example_pool=example_pool,
        embed=embed_documents,
        sorter=sorter,
        train_items=train_items,
        cases=cases,
    )
    print(json.dumps(result.summary(), indent=2))
    if out:
        Path(out).write_text(  # noqa: ASYNC240 - CLI only
            json.dumps(
                {
                    "kind": "classifier",
                    "summary": result.summary(),
                    "per_item_correct": result.per_item_correct(),
                    "per_item_correct_with_sorter": result.per_item_correct(True)
                    if sorter
                    else None,
                    "trials": [dataclasses.asdict(t) for t in result.trials],
                },
                indent=2,
            )
        )


async def cmd_eval_conflicts(
    set_name: str,
    model: str | None,
    tier: str,
    repeats: int,
    out: str | None,
    stage: str = "judge",
    think: bool = False,
    units: bool = False,
    only_flagged: str | None = None,
    strict: bool = False,
    screen: bool = False,
    focus: bool = False,
) -> None:
    import dataclasses
    import json

    from app.eval.conflicts import SETS, evaluate, load_items, search_recall
    from app.models.gateway import build_gateway

    if stage == "search":
        from app.retrieval.embed import embed_documents

        items = load_items(get_settings().config_dir / "eval" / SETS[set_name])
        rows = await search_recall(
            items,
            embed_documents,
            cutoffs=[0.25, 0.3, 0.35, 0.4, 0.45, 0.5, 0.55],
            ks=[3, 5, 10],
        )
        for r in rows:
            print(json.dumps(r))
        if out:
            Path(out).write_text(json.dumps(rows, indent=2))  # noqa: ASYNC240 - CLI only
        return

    from app.retrieval.embed import embed_documents

    gateway = build_gateway()
    if model:
        cfg = gateway.config.tier(tier)
        gateway.config.tiers[tier] = dataclasses.replace(cfg, model=model)
    if think:  # the model's own default (thinking on), with room for the reasoning
        cfg = gateway.config.tier(tier)
        gateway.config.tiers[tier] = dataclasses.replace(
            cfg, think=None, max_tokens=max(cfg.max_tokens, 8192)
        )
    used = gateway.config.tier(tier)
    if used.location != "local":
        sys.exit("the conflict eval runs on local tiers only")
    items = load_items(get_settings().config_dir / "eval" / SETS[set_name])
    only = None
    if only_flagged:  # a confirm stage: check only what the first stage flagged
        first = json.loads(Path(only_flagged).read_text())  # noqa: ASYNC240 - CLI only
        if first["kind"] != f"conflicts-{set_name}":
            sys.exit("--only-flagged must come from a run on the same set")
        only = {(t["item"], t["run"]) for t in first["trials"] if t["got"]}

    def progress(t):
        if not t.correct:
            got = "error" if t.got is None else ("flagged" if t.got else "cleared")
            print(f"  run {t.run + 1} {t.item} ({t.kind}): {got}", flush=True)

    result = await evaluate(
        gateway,
        items,
        model=used.model
        + "".join(
            f" +{n}"
            for n, on in (
                ("think", think),
                ("units", units),
                ("strict", strict),
                ("screen", screen),
                ("focus", focus),
            )
            if on
        ),
        set_name=set_name,
        repeats=repeats,
        tier=tier,
        units=units,
        strict=strict,
        screen=screen,
        embed=embed_documents if focus else None,
        only=only,
        progress=progress,
    )
    if all(t.got is None for t in result.trials):
        sys.exit("every model call failed: is Ollama reachable at OLLAMA_BASE_URL?")
    print(json.dumps(result.summary(), indent=2))
    if out:
        Path(out).write_text(json.dumps(result.to_json(), indent=2))  # noqa: ASYNC240 - CLI only


def cmd_eval_conflicts_cascade(first: str, confirm: str, out: str | None) -> None:
    import json

    from app.eval.conflicts import cascade
    from app.eval.stats import paired

    one, two = (json.loads(Path(x).read_text()) for x in (first, confirm))
    result = cascade(one, two)
    print(json.dumps(result.summary(), indent=2))
    print("first stage alone vs two stages:")
    print(json.dumps(paired(one["per_item_correct"], result.per_item_correct()), indent=2))
    if out:
        Path(out).write_text(json.dumps(result.to_json(), indent=2))


def cmd_compare_evals(a: str, b: str) -> None:
    import json

    from app.eval.stats import paired

    ra, rb = (json.loads(Path(x).read_text()) for x in (a, b))
    if ra["kind"] != rb["kind"]:
        sys.exit("both files must come from the same eval")

    def name(r):
        return r["summary"].get("model") or ",".join(r["summary"].get("models") or [])

    print(f"A = {name(ra)}   B = {name(rb)}")
    print(json.dumps(paired(ra["per_item_correct"], rb["per_item_correct"]), indent=2))


async def cmd_eval_answers(
    model: str | None,
    only: str | None,
    out: str | None,
    repeats: int = 1,
    questions: str = "questions.yaml",
) -> None:
    import dataclasses
    import json

    import yaml

    from app.config import REPO_ROOT
    from app.eval.answers import per_item_correct, run_eval, summarise
    from app.models.gateway import build_gateway
    from app.retrieval.embed import embed_query
    from app.spaces import space_profiles

    gateway = build_gateway()
    tiers = gateway.config.tiers
    if model:  # measure one local candidate on its own, without escalation
        local = dataclasses.replace(tiers["answer-local"], model=model)
        tiers["answer-local"] = local
        tiers["answer"] = dataclasses.replace(local, name="answer")
        tiers.pop("reasoning", None)
    cfg = get_settings().config_dir
    truth = yaml.safe_load((REPO_ROOT / "demo-vault-labels.yaml").read_text())

    def progress(g):
        mark = "ok " if g.correct else "BAD"
        print(
            f"{mark} {g.id:4} {g.set:11} route={','.join(g.routed) or '-'}({g.route_reason})"
            f" {g.total_ms / 1000:5.1f}s {'; '.join(g.notes + g.leak)}",
            flush=True,
        )

    results = await run_eval(
        questions_file=cfg / "eval" / questions,
        roles_config=yaml.safe_load((cfg / "roles.yaml").read_text()),
        truth={**truth["notes"], **truth["attachments"]},
        sessions=get_sessionmaker(),
        gateway=gateway,
        embed_query=embed_query,
        profiles=space_profiles(),
        only=set(only.split(",")) if only else None,
        repeats=repeats,
        progress=progress,
    )
    print(json.dumps(summarise(results), indent=2))
    if out:
        Path(out).write_text(  # noqa: ASYNC240 - CLI only
            json.dumps(
                {
                    "kind": "answers",
                    "summary": summarise(results),
                    "per_item_correct": per_item_correct(results),
                    "trials": [dataclasses.asdict(r) for r in results],
                },
                indent=2,
            )
        )


async def cmd_eval_retrieval(questions: str, only: str | None) -> None:
    import json

    import yaml

    from app.eval.retrieval import run_retrieval_eval, summarise_retrieval
    from app.models.gateway import build_gateway
    from app.retrieval.embed import embed_query
    from app.spaces import space_profiles

    cfg = get_settings().config_dir
    rows = await run_retrieval_eval(
        questions_file=cfg / "eval" / questions,
        roles_config=yaml.safe_load((cfg / "roles.yaml").read_text()),
        sessions=get_sessionmaker(),
        gateway=build_gateway(),
        embed_query=embed_query,
        profiles=space_profiles(),
        only=set(only.split(",")) if only else None,
    )
    for r in rows:
        if not r.all_facts or not r.doc_hit:
            print(f"  {r.id:4} recall {r.fact_recall:.0%} doc_hit={r.doc_hit} missing={r.missing}")
    print(json.dumps(summarise_retrieval(rows), indent=2))


async def cmd_seed_demo() -> None:
    _require_dev()
    async with get_sessionmaker()() as s:
        await sync_spaces(s)
        await sync_roles(s)
        for email, name, roles, home in DEMO_USERS:
            if await get_user_by_email(s, email):
                continue
            user, _ = await create_user(
                s, email=email, display_name=name, role_names=roles, home_space=home, actor_id=None
            )
            user.password_hash = passwords.hash_password(DEMO_PASSWORD)
            user.totp_secret_enc = totp.encrypt_secret(_demo_totp_secret(email))
            user.totp_enabled = True
        await s.commit()
    print(f"demo users ready (password: {DEMO_PASSWORD}); index the vault with `index`")
    print("two-factor codes: python -m app.cli totp-code EMAIL")


def cmd_totp_code(email: str) -> None:
    _require_dev()
    if email not in {u[0] for u in DEMO_USERS}:
        sys.exit("only demo users")
    print(pyotp.TOTP(_demo_totp_secret(email)).now())


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("sync-config")
    p.add_argument("--reset-roles", action="store_true")
    p = sub.add_parser("create-admin")
    p.add_argument("email")
    p.add_argument("name")
    p = sub.add_parser("index")
    p.add_argument("--full", action="store_true")
    p.add_argument("--no-embed", action="store_true")
    p = sub.add_parser("classify")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--model", default=None)
    sub.add_parser("train-sorter")
    p = sub.add_parser("eval-classifier")
    p.add_argument("--model", default=None)
    p.add_argument("--tier", default="classifier")
    p.add_argument("--repeats", type=int, default=1)
    p.add_argument("--show-folders", action="store_true", help="not blind: show real paths")
    p.add_argument("--example-pool", type=int, default=None, help="N human-labelled notes")
    p.add_argument("--sorter", action="store_true", help="also score with the trained sorter")
    p.add_argument("--cases", choices=["dev", "holdout"], default="dev")
    p.add_argument("--out", default=None)
    p = sub.add_parser("eval-retrieval")
    p.add_argument("--questions", default="questions.yaml")
    p.add_argument("--only", default=None)
    p = sub.add_parser("eval-conflicts")
    p.add_argument("--stage", choices=["judge", "search"], default="judge")
    p.add_argument(
        "--set",
        dest="set_name",
        choices=["dev", "holdout", "holdout2", "holdout3", "holdout4"],
        default="dev",
    )
    p.add_argument("--model", default=None)
    p.add_argument("--tier", default="background")
    p.add_argument("--repeats", type=int, default=1)
    p.add_argument("--out", default=None)
    p.add_argument("--think", action="store_true", help="leave the model's thinking on")
    p.add_argument("--units", action="store_true", help="add unit conversions first")
    p.add_argument("--only-flagged", default=None, help="saved run: check only its flags")
    p.add_argument("--strict", action="store_true", help="unstated group overrides count")
    p.add_argument("--screen", action="store_true", help="first-stage wording: flag if unsure")
    p.add_argument("--focus", action="store_true", help="show the most alike sentences first")
    p = sub.add_parser("eval-conflicts-cascade")
    p.add_argument("first")
    p.add_argument("confirm")
    p.add_argument("--out", default=None)
    p = sub.add_parser("compare-evals")
    p.add_argument("a")
    p.add_argument("b")
    p = sub.add_parser("eval-answers")
    p.add_argument("--model", default=None)
    p.add_argument("--repeats", type=int, default=1)
    p.add_argument("--questions", default="questions.yaml", help="file in config/eval/")
    p.add_argument("--only", default=None)
    p.add_argument("--out", default=None)
    p = sub.add_parser("accept-invite")
    p.add_argument("token")
    sub.add_parser("seed-demo")
    p = sub.add_parser("totp-code")
    p.add_argument("email")
    args = parser.parse_args(argv)

    if args.cmd == "totp-code":
        return cmd_totp_code(args.email)

    async def run() -> None:
        try:
            if args.cmd == "sync-config":
                await cmd_sync_config(args.reset_roles)
            elif args.cmd == "create-admin":
                await cmd_create_admin(args.email, args.name)
            elif args.cmd == "accept-invite":
                await cmd_accept_invite(args.token)
            elif args.cmd == "index":
                await cmd_index(args.full, args.no_embed)
            elif args.cmd == "classify":
                await cmd_classify(args.limit, args.model)
            elif args.cmd == "train-sorter":
                from app.classify.training import train_sorter

                print(await train_sorter(get_sessionmaker()))
            elif args.cmd == "eval-classifier":
                await cmd_eval_classifier(
                    args.model,
                    args.tier,
                    args.repeats,
                    not args.show_folders,
                    args.out,
                    args.example_pool,
                    args.sorter,
                    args.cases,
                )
            elif args.cmd == "eval-retrieval":
                await cmd_eval_retrieval(args.questions, args.only)
            elif args.cmd == "eval-conflicts":
                await cmd_eval_conflicts(
                    args.set_name,
                    args.model,
                    args.tier,
                    args.repeats,
                    args.out,
                    args.stage,
                    args.think,
                    args.units,
                    args.only_flagged,
                    args.strict,
                    args.screen,
                    args.focus,
                )
            elif args.cmd == "compare-evals":
                cmd_compare_evals(args.a, args.b)
            elif args.cmd == "eval-conflicts-cascade":
                cmd_eval_conflicts_cascade(args.first, args.confirm, args.out)
            elif args.cmd == "eval-answers":
                await cmd_eval_answers(
                    args.model, args.only, args.out, args.repeats, args.questions
                )
            elif args.cmd == "seed-demo":
                await cmd_seed_demo()
        finally:
            await get_engine().dispose()

    asyncio.run(run())


if __name__ == "__main__":
    main()
