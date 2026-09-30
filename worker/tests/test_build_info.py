from unittest.mock import patch


def test_worker_inspection_reads_its_own_image_identity():
    from tasks import build_info
    with patch.object(build_info, 'read_build_info', return_value={'component': 'worker', 'revision': 'a' * 40}) as read:
        assert build_info.photostore_build_info(None)['revision'] == 'a' * 40
    read.assert_called_once_with('worker')
