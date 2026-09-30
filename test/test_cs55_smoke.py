import sys
from pathlib import Path
import torch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'src'
sys.path.insert(0, str(SRC))

from cs55_demo import load_config
from cs55_demo.pipeline_runner import run_full_pipeline


class DummyEmbedder:
    """Deterministic lightweight embedder for packaging tests only."""
    def embed(self, image_path):
        data = Path(image_path).read_bytes()
        vals = [sum(data[i::8]) % 997 for i in range(8)]
        v = torch.tensor(vals, dtype=torch.float32).reshape(1, -1)
        return torch.nn.functional.normalize(v, p=2, dim=-1)


def test_smoke():
    config = load_config(ROOT / 'config.sample.json')
    result, bundle = run_full_pipeline(
        config,
        use_cache=False,
        embedder=DummyEmbedder(),
    )
    assert result['dataset_name'] == 'SampleDemo'
    assert result['evidence_chain']['artefact_count'] == 6
    assert result['evidence_chain']['relationship_count'] == 5
    assert 0 <= result['final_score']['integrity'] <= 1
    assert 0 <= result['final_score']['completeness'] <= 1
    assert 0 <= result['chain_metrics']['confidence'] <= 1
    assert 0 <= result['chain_metrics']['coverage'] <= 1
    assert set(result['provenance']) == {'storyboard', 'animatic', 'final'}
    expected_provenance_status = {
        'File Integrity': 'available',
        'C2PA Provenance': 'not_available',
        'Source Project Evidence': 'not_available',
        'Editing / AI Transparency': 'not_available',
    }
    assert result['provenance_authenticity_evidence'] == {
        asset_name: expected_provenance_status
        for asset_name in ('storyboard', 'animatic', 'final')
    }
    assert (
        bundle['provenance_authenticity_evidence']
        == result['provenance_authenticity_evidence']
    )
    assert bundle['provenance'] == result['provenance']
    assert (
        bundle['final_artefact_hash']
        == result['provenance']['final']['file_hash']['value']
    )
    assert bundle['hash_method'] == 'sha256'


if __name__ == '__main__':
    test_smoke()
    print('CS55_1_demo smoke test passed')
