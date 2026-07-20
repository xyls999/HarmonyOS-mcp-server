from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


def source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


class FaceDoorContractTest(unittest.TestCase):
    def test_face_api_uses_dedicated_tls_service_and_all_contract_routes(self) -> None:
        api = source("entry/src/main/ets/api/faceDoorApi.ets")
        self.assertIn("https://192.168.1.138:5001", api)
        self.assertIn("caData: FACE_DOOR_CA", api)
        for route in (
            "/api/door/open",
            "/api/recognize",
            "/api/faces/register",
            "/api/faces/delete",
            "/api/faces",
            "/api/door/status",
            "/api/faces/reload",
            "/api/health",
        ):
            self.assertIn(route, api)

    def test_open_door_upload_is_multipart_and_has_no_password(self) -> None:
        api = source("entry/src/main/ets/api/faceDoorApi.ets")
        self.assertIn('name="image"', api)
        self.assertIn("multipart/form-data; boundary=", api)
        self.assertNotIn("doorPassword", api)
        self.assertNotIn("hardcoded door password", api.lower())

    def test_camera_is_real_front_camera_photo_capture(self) -> None:
        camera = source("entry/src/main/ets/api/faceCamera.ets")
        self.assertIn("ohos.permission.CAMERA", camera)
        self.assertIn("CAMERA_POSITION_FRONT", camera)
        self.assertIn("createPreviewOutput", camera)
        self.assertIn("createPhotoOutput", camera)
        self.assertIn("photoAvailable", camera)
        self.assertIn("ComponentType.JPEG", camera)

    def test_camera_does_not_query_preview_rotation_before_session_commit(self) -> None:
        camera = source("entry/src/main/ets/api/faceCamera.ets")
        self.assertNotIn(
            "setPreviewRotation(this.previewOutput.getPreviewRotation",
            camera,
        )

    def test_login_and_account_both_expose_face_door(self) -> None:
        login = source("entry/src/main/ets/pages/LoginPage.ets")
        mine = source("entry/src/main/ets/pages/MinePage.ets")
        index = source("entry/src/main/ets/pages/Index.ets")
        self.assertIn("刷脸开门", login)
        self.assertIn("人脸门禁", mine)
        self.assertIn("FaceDoorPage", index)

    def test_scan_autocaptures_and_detection_failure_retries(self) -> None:
        page = source("entry/src/main/ets/pages/FaceDoorPage.ets")
        self.assertIn("this.capture()", page)
        self.assertIn("result.stage === 'detection'", page)
        self.assertIn("this.retryCount < 2", page)
        self.assertIn("FaceDoorApi.reload()", page)


if __name__ == "__main__":
    unittest.main()
