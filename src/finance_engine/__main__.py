"""Allow ``python -m finance_engine`` as an alternative to the console script."""

from finance_engine.cli import main

raise SystemExit(main())
