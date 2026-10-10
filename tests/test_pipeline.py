import pandas as pd
import pytest

from hackathon.main import main
from hackathon.pipeline import Pipeline
from hackathon.stages.ingest import ingest
from hackathon.stages.transform import transform
from hackathon.stages.validate import validate


def test_pipeline_runs_stages_in_order():
    p = Pipeline([("add", lambda x: x + 1), ("double", lambda x: x * 2)])
    assert p.run(1) == 4


def test_ingest_rejects_unknown_extension(tmp_path):
    f = tmp_path / "data.xyz"
    f.write_text("x")
    with pytest.raises(ValueError):
        ingest(f)


def test_validate_missing_column():
    with pytest.raises(ValueError):
        validate(pd.DataFrame({"a": [1]}), required_columns=["b"])


def test_validate_empty():
    with pytest.raises(ValueError):
        validate(pd.DataFrame())


def test_transform_cleans_columns_and_duplicates():
    df = pd.DataFrame({" First Name ": ["a", "a"], "Age": [1, 1]})
    out = transform(df)
    assert list(out.columns) == ["first_name", "age"]
    assert len(out) == 1


def test_end_to_end(tmp_path):
    src, dst = tmp_path / "in.csv", tmp_path / "out" / "out.csv"
    src.write_text("A B,C\n1,2\n1,2\n3,4\n")
    assert main(["--input", str(src), "--output", str(dst), "--config", "config/config.yaml"]) == 0
    assert len(pd.read_csv(dst)) == 2
