# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Same-origin uploads (USE_MINIO=1): presign against the request host, talk to MinIO internally."""

import os
from unittest.mock import Mock, patch

import pytest

from plane.settings.storage import S3Storage

MINIO_ENV = {
    "USE_MINIO": "1",
    "AWS_ACCESS_KEY_ID": "k",
    "AWS_SECRET_ACCESS_KEY": "s",
    "AWS_S3_BUCKET_NAME": "uploads",
    "AWS_S3_ENDPOINT_URL": "http://plane-minio:9000",
}


def _request(host="phone.example.test:3300", scheme="http"):
    request = Mock()
    request.scheme = scheme
    request.get_host.return_value = host
    return request


def _clients(mock_boto3):
    presign, server = Mock(name="presign"), Mock(name="server")
    mock_boto3.client.side_effect = [presign, server]
    return presign, server


@pytest.mark.unit
class TestSameOriginStorage:
    @patch.dict(os.environ, MINIO_ENV, clear=True)
    @patch("plane.settings.storage.boto3")
    def test_presign_uses_request_host_and_server_calls_use_internal_endpoint(self, mock_boto3):
        presign, server = _clients(mock_boto3)
        storage = S3Storage(request=_request())

        endpoints = [c.kwargs["endpoint_url"] for c in mock_boto3.client.call_args_list]
        assert endpoints == ["http://phone.example.test:3300", "http://plane-minio:9000"]

        storage.generate_presigned_post("ws/a.png", "image/png", 10)
        storage.generate_presigned_url("ws/a.png")
        assert presign.generate_presigned_post.called and presign.generate_presigned_url.called

        storage.get_object_metadata("ws/a.png")
        storage.copy_object("ws/a.png", "ws/b.png")
        storage.upload_file(Mock(), "ws/c.png", "image/png", extra_args={})
        storage.delete_files(["ws/a.png"])
        for name in ("head_object", "copy_object", "upload_fileobj", "delete_objects"):
            assert getattr(server, name).called, name
            assert not getattr(presign, name).called, name

    @patch.dict(os.environ, MINIO_ENV, clear=True)
    @patch("plane.settings.storage.boto3")
    def test_without_request_a_single_internal_client_is_used(self, mock_boto3):
        mock_boto3.client.return_value = Mock()
        storage = S3Storage()
        assert mock_boto3.client.call_count == 1
        assert mock_boto3.client.call_args.kwargs["endpoint_url"] == "http://plane-minio:9000"
        assert storage.s3_server_client is storage.s3_client

    @patch.dict(os.environ, {**MINIO_ENV, "USE_MINIO": "0"}, clear=True)
    @patch("plane.settings.storage.boto3")
    def test_non_minio_mode_is_unchanged(self, mock_boto3):
        mock_boto3.client.return_value = Mock()
        storage = S3Storage(request=_request())
        assert mock_boto3.client.call_count == 1
        assert mock_boto3.client.call_args.kwargs["endpoint_url"] == "http://plane-minio:9000"
        assert storage.s3_server_client is storage.s3_client
