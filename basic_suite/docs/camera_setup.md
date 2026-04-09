# Camera Setup & Discovery

Guide for connecting your hardware cameras (ONVIF/RTSP) to the SecureVu Basic Suite.

## 1. Quick Config (Webcam or RTSP)

The suite is designed to quickly target a primary stream using environment variables:

### Environmental Override
```bash
export BASIC_MAIN_CAMERA="rtsp://USERNAME:PASSWORD@CAMERA_IP:554/stream_path"
```

### Common RTSP Paths
- **Dahua/Amcrest**: `rtsp://user:pass@IP:554/cam/realmonitor?channel=1&subtype=0`
- **Hikvision**: `rtsp://user:pass@IP:554/Streaming/Channels/101`
- **TP-Link/VIGI**: `rtsp://user:pass@IP:554/live/ch00_0`

## 2. Discovery Helper

If you don't know the IP of your ONVIF cameras, use the discovery tool:

```bash
# Scan a specific subnet
python3 basic_suite/pipeline/discovery_onvif_rtsp.py --cidr 192.168.1.0/24
```

## 3. Persistent Camera List

For multi-camera setups, edit `config/cameras.basic.yaml`:

```yaml
cameras:
  cam1:
    url: "rtsp://..."
    name: "Front Gate"
    onvif:
       url: "http://IP:8080"
       username: "admin"
       password: "..."
```

## 4. Codec Compatibility
Ensure your camera is set to **H.264**. 
- H.265 (HEVC) is not supported by standard browser MJPEG streaming and may cause high CPU load if transcoding is required.
