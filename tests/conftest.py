import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lightning.config import load_params
from lightning.data.synthetic import generate
from lightning.features import build_features


@pytest.fixture(scope="session")
def params():
    return load_params()


@pytest.fixture(scope="session")
def synth():
    return generate(years=2.5, seed=11)


@pytest.fixture(scope="session")
def feats(synth, params):
    fut, daily = synth
    return build_features(fut, daily, params)
