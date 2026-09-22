"""Load the actual standalone library. Copyright 2026 Gabriele Pennacchia."""

import importlib.util
import sys
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "custom_components/dreame_mf10_flux/api"
if "mf10_flux" not in sys.modules:
    spec = importlib.util.spec_from_file_location(
        "mf10_flux", SOURCE / "__init__.py", submodule_search_locations=[str(SOURCE)]
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
