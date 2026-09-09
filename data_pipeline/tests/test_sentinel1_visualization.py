import numpy as np

from data_pipeline.imagery.sentinel1_visualization import backscatter_to_display


def test_sentinel1_display_is_deterministic_and_does_not_reconstruct_invalid_pixels():
    source = np.array([[0.0, np.nan, 0.01], [0.1, 1.0, 10.0]], dtype=np.float32)

    first = backscatter_to_display(source)

    assert first.dtype == np.uint8
    assert first[0, 0] == 0
    assert first[0, 1] == 0
    assert np.array_equal(first, backscatter_to_display(source))
