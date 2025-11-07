# Bilibili直播录制工具

## 功能特性
- 录制Bilibili直播间视频
- 抓取直播间弹幕
- 支持指定录制时长
- Web界面管理录制任务

## 环境要求
- Python 3.7+
- FFmpeg
- Windows/Linux/macOS

## 安装步骤

### 1. 安装Python依赖
```bash
pip install -r requirements.txt
```

### 2. 安装FFmpeg
**重要：必须先安装FFmpeg才能录制视频！**

#### Windows:
1. 访问 https://www.gyan.dev/ffmpeg/builds/
2. 下载 "ffmpeg-git-full.7z" 文件
3. 解压文件到任意目录
4. 将解压目录下的 bin 文件夹路径添加到系统环境变量PATH中
   或者将 bin 文件夹中的 ffmpeg.exe 复制到系统 System32 目录下

#### macOS (使用Homebrew):
```bash
brew install ffmpeg
```

#### Ubuntu/Debian:
```bash
sudo apt update
sudo apt install ffmpeg
```

### 3. 验证FFmpeg安装
```bash
ffmpeg -version
```

## 使用方法

### 启动Web服务
```bash
python app.py
```

然后在浏览器中访问 http://localhost:8000

### 使用API录制
```bash
# 开始录制
curl -X POST http://localhost:8000/api/record/start \
  -H "Content-Type: application/json" \
  -d '{"room_id": "35", "duration_seconds": 120}'

# 停止录制
curl -X POST http://localhost:8000/api/record/stop \
  -H "Content-Type: application/json" \
  -d '{"task_id": "任务ID"}'
```

## 项目结构
- `app.py`: 主程序入口
- `recorder/`: 录制功能模块
- `web/`: Web界面文件
- `outputs/`: 录制文件输出目录

## 输出文件
录制的视频和弹幕文件将保存在 `outputs/` 目录下，按直播间ID分类存储。