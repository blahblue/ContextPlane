"""Load the repository-scoped coding-agent demo corpus."""

from pathlib import Path

from sqlalchemy.orm import Session

from contextplane.context_registry.seed import load_seed_file
from contextplane.database import build_engine
from contextplane.settings import Settings

FIXTURE = Path(__file__).with_name("context.yaml")


def main() -> None:
    """Apply the demo seed to the configured ContextPlane database."""
    engine = build_engine(Settings())
    try:
        with Session(engine) as session:
            results = load_seed_file(session, FIXTURE)
            session.commit()
    finally:
        engine.dispose()

    for result in results:
        print(
            f"{result.status}: {result.tenant_id}/{result.key} "
            f"version={result.version}"
        )


if __name__ == "__main__":
    main()
