import { abilityAccessCtrl, common, Permissions } from '@kit.AbilityKit';
import { camera } from '@kit.CameraKit';
import { image } from '@kit.ImageKit';
import { BusinessError } from '@kit.BasicServicesKit';
import { hilog } from '@kit.PerformanceAnalysisKit';

const CAMERA_PERMISSION: Permissions = 'ohos.permission.CAMERA';

export interface FaceCameraCallbacks {
  onReady: () => void;
  onPhoto: (data: ArrayBuffer) => void;
  onError: (message: string) => void;
}

export class FaceCamera {
  private input: camera.CameraInput | null = null;
  private previewOutput: camera.PreviewOutput | null = null;
  private photoOutput: camera.PhotoOutput | null = null;
  private session: camera.PhotoSession | null = null;
  private callbacks: FaceCameraCallbacks | null = null;
  private started: boolean = false;
  private capturing: boolean = false;

  private async requestPermission(context: common.Context): Promise<boolean> {
    try {
      const permissions: Array<Permissions> = [CAMERA_PERMISSION];
      const result = await abilityAccessCtrl.createAtManager().requestPermissionsFromUser(context, permissions);
      return result.authResults.length > 0 && result.authResults[0] === 0;
    } catch (error) {
      const err = error as BusinessError;
      hilog.error(0x0000, 'FaceCamera', 'camera permission failed: %{public}s', err.message);
      return false;
    }
  }

  private selectFront(cameras: camera.CameraDevice[]): camera.CameraDevice | null {
    for (const device of cameras) {
      if (device.cameraPosition === camera.CameraPosition.CAMERA_POSITION_FRONT) return device;
    }
    return null;
  }

  private selectPreview(profiles: camera.Profile[]): camera.Profile | null {
    if (profiles.length === 0) return null;
    let selected = profiles[0];
    let bestScore = Number.MAX_VALUE;
    for (const profile of profiles) {
      const ratio = profile.size.width / Math.max(1, profile.size.height);
      const area = profile.size.width * profile.size.height;
      const score = Math.abs(ratio - 0.75) * 1000000 + Math.abs(area - 640 * 480);
      if (score < bestScore) {
        selected = profile;
        bestScore = score;
      }
    }
    return selected;
  }

  private selectPhoto(profiles: camera.Profile[]): camera.Profile | null {
    let selected: camera.Profile | null = null;
    let bestScore = Number.MAX_VALUE;
    for (const profile of profiles) {
      if (profile.format !== camera.CameraFormat.CAMERA_FORMAT_JPEG) continue;
      const area = profile.size.width * profile.size.height;
      const score = Math.abs(area - 640 * 480);
      if (score < bestScore) {
        selected = profile;
        bestScore = score;
      }
    }
    return selected;
  }

  async start(context: common.Context, surfaceId: string, callbacks: FaceCameraCallbacks): Promise<void> {
    if (this.started) return;
    this.callbacks = callbacks;
    if (!await this.requestPermission(context)) {
      callbacks.onError('请允许相机权限后重试');
      return;
    }
    try {
      const manager = camera.getCameraManager(context);
      const front = this.selectFront(manager.getSupportedCameras());
      if (!front) throw new Error('未找到前置摄像头');
      const capability = manager.getSupportedOutputCapability(front, camera.SceneMode.NORMAL_PHOTO);
      const previewProfile = this.selectPreview(capability.previewProfiles);
      const photoProfile = this.selectPhoto(capability.photoProfiles);
      if (!previewProfile || !photoProfile) throw new Error('当前设备不支持所需拍照格式');

      this.input = manager.createCameraInput(front);
      await this.input.open();
      this.previewOutput = manager.createPreviewOutput(previewProfile, surfaceId);
      this.photoOutput = manager.createPhotoOutput(photoProfile);
      this.photoOutput.on('photoAvailable', async (error: BusinessError, photo: camera.Photo): Promise<void> => {
        if (error) {
          this.capturing = false;
          if (this.callbacks) this.callbacks.onError(error.message || '拍照失败，请重试');
          return;
        }
        await this.handlePhoto(photo);
      });
      this.session = manager.createSession<camera.PhotoSession>(camera.SceneMode.NORMAL_PHOTO);
      this.session.beginConfig();
      this.session.addInput(this.input);
      this.session.addOutput(this.previewOutput);
      this.session.addOutput(this.photoOutput);
      await this.session.commitConfig();
      await this.session.start();
      this.started = true;
      hilog.info(0x0000, 'FaceCamera', 'front camera ready preview=%{public}dx%{public}d photo=%{public}dx%{public}d',
        previewProfile.size.width, previewProfile.size.height, photoProfile.size.width, photoProfile.size.height);
      callbacks.onReady();
    } catch (error) {
      const err = error as Error;
      hilog.error(0x0000, 'FaceCamera', 'camera start failed: %{public}s', err.message);
      callbacks.onError(err.message || '无法启用前置摄像头');
      await this.release();
    }
  }

  async capture(): Promise<void> {
    if (!this.started || !this.photoOutput || this.capturing) return;
    this.capturing = true;
    try {
      const setting: camera.PhotoCaptureSetting = {
        quality: camera.QualityLevel.QUALITY_LEVEL_MEDIUM,
        rotation: this.photoOutput.getPhotoRotation(0)
      };
      await this.photoOutput.capture(setting);
    } catch (error) {
      const err = error as BusinessError;
      this.capturing = false;
      if (this.callbacks) this.callbacks.onError(err.message || '拍照失败，请重试');
    }
  }

  private async handlePhoto(photo: camera.Photo): Promise<void> {
    try {
      const component = await photo.main.getComponent(image.ComponentType.JPEG);
      hilog.info(0x0000, 'FaceCamera', 'photo captured bytes=%{public}d', component.byteBuffer.byteLength);
      if (this.callbacks) this.callbacks.onPhoto(component.byteBuffer);
    } catch (error) {
      const err = error as BusinessError;
      if (this.callbacks) this.callbacks.onError(err.message || '读取照片失败');
    } finally {
      this.capturing = false;
      try { await photo.release(); } catch (_) {}
    }
  }

  async release(): Promise<void> {
    this.started = false;
    this.capturing = false;
    this.callbacks = null;
    if (this.photoOutput) {
      try { this.photoOutput.off('photoAvailable'); } catch (_) {}
    }
    if (this.session) {
      try { await this.session.stop(); } catch (_) {}
      try { await this.session.release(); } catch (_) {}
    }
    if (this.previewOutput) {
      try { await this.previewOutput.release(); } catch (_) {}
    }
    if (this.photoOutput) {
      try { await this.photoOutput.release(); } catch (_) {}
    }
    if (this.input) {
      try { await this.input.close(); } catch (_) {}
    }
    this.session = null;
    this.previewOutput = null;
    this.photoOutput = null;
    this.input = null;
  }
}
