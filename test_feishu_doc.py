from types import SimpleNamespace

import feishu_doc
from feishu_doc import FeishuDocManager


class FakeConfig:
    def __init__(self, app_id="", app_secret="", folder_token=""):
        self.feishu_app_id = app_id
        self.feishu_app_secret = app_secret
        self.feishu_folder_token = folder_token


class FakeBuilt:
    def __init__(self, attrs):
        self.attrs = dict(attrs)


class FakeBuilder:
    def __init__(self):
        self.attrs = {}

    def __getattr__(self, name):
        def method(*args):
            self.attrs[name] = args[0] if len(args) == 1 else args
            return self

        return method

    def build(self):
        return FakeBuilt(self.attrs)


class FakeSdkType:
    @staticmethod
    def builder():
        return FakeBuilder()


def _patch_builder_types(monkeypatch, names):
    for name in names:
        monkeypatch.setattr(feishu_doc, name, FakeSdkType)


def test_manager_skips_client_when_config_is_incomplete(monkeypatch):
    monkeypatch.setattr(feishu_doc, "get_config", lambda: FakeConfig(app_id="app", app_secret="", folder_token="folder"))

    manager = FeishuDocManager()

    assert manager.is_configured() is False
    assert manager.client is None
    assert manager.create_daily_doc("Daily", "# Content") is None


def test_manager_builds_client_when_configured(monkeypatch):
    builder_calls = []

    class FakeClient:
        @staticmethod
        def builder():
            return FakeClientBuilder()

    class FakeClientBuilder:
        def app_id(self, value):
            builder_calls.append(("app_id", value))
            return self

        def app_secret(self, value):
            builder_calls.append(("app_secret", value))
            return self

        def log_level(self, value):
            builder_calls.append(("log_level", value))
            return self

        def build(self):
            return "client"

    monkeypatch.setattr(feishu_doc, "get_config", lambda: FakeConfig("app", "secret", "folder"))
    monkeypatch.setattr(feishu_doc.lark, "Client", FakeClient)

    manager = FeishuDocManager()

    assert manager.is_configured() is True
    assert manager.client == "client"
    assert builder_calls[:2] == [("app_id", "app"), ("app_secret", "secret")]


def test_markdown_to_sdk_blocks_maps_headings_dividers_and_text(monkeypatch):
    _patch_builder_types(
        monkeypatch,
        ["Block", "Divider", "TextRun", "TextElementStyle", "TextElement", "Text", "TextStyle"],
    )
    manager = object.__new__(FeishuDocManager)

    blocks = manager._markdown_to_sdk_blocks("# H1\n## H2\n### H3\n---\nplain text\n\n")

    assert [block.attrs["block_type"] for block in blocks] == [3, 4, 5, 22, 2]
    assert "heading1" in blocks[0].attrs
    assert "heading2" in blocks[1].attrs
    assert "heading3" in blocks[2].attrs
    assert "divider" in blocks[3].attrs
    assert "text" in blocks[4].attrs


def test_create_daily_doc_writes_content_in_batches(monkeypatch):
    _patch_builder_types(
        monkeypatch,
        [
            "CreateDocumentRequest",
            "CreateDocumentRequestBody",
            "CreateDocumentBlockChildrenRequest",
            "CreateDocumentBlockChildrenRequestBody",
        ],
    )

    class FakeResponse:
        code = 0
        msg = "ok"
        error = ""

        def success(self):
            return True

        data = SimpleNamespace(document=SimpleNamespace(document_id="doc123"))

    class FakeWriteResponse:
        code = 0
        msg = "ok"

        def success(self):
            return True

    created_requests = []
    write_requests = []

    client = SimpleNamespace(
        docx=SimpleNamespace(
            v1=SimpleNamespace(
                document=SimpleNamespace(create=lambda request: created_requests.append(request) or FakeResponse()),
                document_block_children=SimpleNamespace(
                    create=lambda request: write_requests.append(request) or FakeWriteResponse()
                ),
            )
        )
    )

    manager = object.__new__(FeishuDocManager)
    manager.app_id = "app"
    manager.app_secret = "secret"
    manager.folder_token = "folder"
    manager.client = client
    monkeypatch.setattr(manager, "_markdown_to_sdk_blocks", lambda content: list(range(51)))

    url = manager.create_daily_doc("Daily", "content")

    assert url == "https://feishu.cn/docx/doc123"
    assert len(created_requests) == 1
    assert len(write_requests) == 2
    assert write_requests[0].attrs["request_body"].attrs["children"] == list(range(50))
    assert write_requests[1].attrs["request_body"].attrs["children"] == [50]
