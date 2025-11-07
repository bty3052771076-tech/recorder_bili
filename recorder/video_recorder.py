import subprocess
import os
import signal
import time
import shutil

class VideoRecorder:
    def __init__(self, stream_url, output_file, ffmpeg_path=None):
        self.stream_url = stream_url
        self.output_file = output_file
        # 如果没有指定ffmpeg路径，则尝试在系统PATH中查找
        self.ffmpeg_path = ffmpeg_path or self._find_ffmpeg()
        self.process = None

    def _find_ffmpeg(self):
        """查找系统中的ffmpeg可执行文件"""
        # 首先检查系统PATH中是否有ffmpeg
        ffmpeg_executable = shutil.which("ffmpeg")
        if ffmpeg_executable:
            return ffmpeg_executable
        # 如果没有找到，返回默认值
        return "ffmpeg"

    def start(self):
        # 确保输出目录存在
        output_dir = os.path.dirname(self.output_file)
        os.makedirs(output_dir, exist_ok=True)
        
        # 构建ffmpeg命令 - 使用兼容FLV的编码器
        cmd = [
            self.ffmpeg_path,
            "-user_agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "-headers", "Referer: https://live.bilibili.com/35",
            "-i", self.stream_url,
            "-c", "copy",       # 直接复制流，不重新编码（最快且兼容性最好）
            "-f", "flv",        # 输出格式为FLV
            "-t", str(self._get_duration_from_stream_url()),  # 持续时间，避免无限录制
            "-y",               # 覆盖输出文件
            self.output_file
        ]
        
        print(f"开始录制视频: {self.output_file}")
        print(f"FFmpeg路径: {self.ffmpeg_path}")
        print(f"命令: {' '.join(cmd)}")
        
        # 检查ffmpeg是否可用
        try:
            subprocess.run([self.ffmpeg_path, "-version"], 
                          stdout=subprocess.DEVNULL, 
                          stderr=subprocess.DEVNULL, 
                          check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            print(f"错误: 找不到FFmpeg或FFmpeg路径不正确: {self.ffmpeg_path}")
            return
        
        # 启动ffmpeg进程
        try:
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
                # 在Windows上不使用shell=True，避免路径问题
            )
        except Exception as e:
            print(f"启动FFmpeg进程失败: {e}")
            return
        
        print(f"FFmpeg进程已启动，PID: {self.process.pid}")
    
    def _get_duration_from_stream_url(self):
        # 从流URL中获取录制时长，这里简单返回一个默认值
        # 在实际应用中，应该从任务配置中获取时长
        return 35  # 返回35秒，比预期稍长一点以确保完整录制

    def stop(self):
        if self.process and self.process.poll() is None:
            # 终止ffmpeg进程
            try:
                self.process.terminate()
                stdout, stderr = self.process.communicate(timeout=10)
                if stdout:
                    print(f"FFmpeg stdout: {stdout.decode('utf-8', errors='ignore')}")
                if stderr:
                    print(f"FFmpeg stderr: {stderr.decode('utf-8', errors='ignore')}")
            except subprocess.TimeoutExpired:
                # 如果进程没有正常退出，强制杀死
                self.process.kill()
                stdout, stderr = self.process.communicate()
                if stdout:
                    print(f"FFmpeg stdout: {stdout.decode('utf-8', errors='ignore')}")
                if stderr:
                    print(f"FFmpeg stderr: {stderr.decode('utf-8', errors='ignore')}")
            
            print(f"停止录制视频: {self.output_file}")
            
            # 检查文件是否创建成功
            if os.path.exists(self.output_file):
                file_size = os.path.getsize(self.output_file)
                print(f"录制文件大小: {file_size} 字节")
            else:
                print(f"警告: 录制文件未创建 {self.output_file}")
        elif self.process:
            print(f"FFmpeg进程已经结束，返回码: {self.process.returncode}")
        else:
            print("FFmpeg进程未启动")