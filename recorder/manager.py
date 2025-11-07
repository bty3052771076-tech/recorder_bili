import os
import json
import time
import asyncio
from datetime import datetime
from recorder.video_recorder import VideoRecorder
from recorder.danmu_client import DanmuClient
from recorder.config import Config

class RecordingTask:
    def __init__(self, task_id, room_id, stream_url=None, duration_seconds=None, output_dir=None):
        self.task_id = task_id
        self.room_id = room_id
        self.stream_url = stream_url
        self.duration_seconds = duration_seconds
        self.output_dir = output_dir or Config.OUTPUT_DIR
        self.status = "pending"
        self.start_time = None
        self.end_time = None
        self.video_file = None
        self.danmaku_file = None
        self.video_recorder = None
        self.danmu_client = None
        self.record_progress = 0  # 录制进度（百分比）
        self.convert_progress = 0  # 转换进度（百分比）
        self.elapsed_time = 0  # 已录制时间（秒）

    async def start(self):
        self.status = "recording"
        self.start_time = datetime.now()
        
        # 生成文件名
        timestamp = self.start_time.strftime("%Y%m%d_%H%M%S")
        room_dir = os.path.join(self.output_dir, str(self.room_id))
        os.makedirs(room_dir, exist_ok=True)
        
        self.video_file = os.path.join(room_dir, f"{self.room_id}_{timestamp}.flv")
        self.danmaku_file = os.path.join(room_dir, f"{self.room_id}_{timestamp}_danmaku.jsonl")
        
        # 启动视频录制
        self.video_recorder = VideoRecorder(self.stream_url, self.video_file, Config.FFMPEG_PATH)
        self.video_recorder.start()
        
        # 启动弹幕抓取
        self.danmu_client = DanmuClient(self.room_id, self.danmaku_file)
        self.danmu_client.start()
        
        # 启动进度更新任务
        asyncio.create_task(self._update_progress())
        
        # 如果设置了录制时长，启动定时停止任务
        if self.duration_seconds:
            asyncio.create_task(self._schedule_stop())

    async def _update_progress(self):
        """定期更新录制进度"""
        while self.status == "recording":
            if self.start_time:
                self.elapsed_time = (datetime.now() - self.start_time).total_seconds()
                if self.duration_seconds:
                    self.record_progress = min(100, int((self.elapsed_time / self.duration_seconds) * 100))
                else:
                    self.record_progress = -1  # 表示无限制录制
            
            await asyncio.sleep(1)  # 每秒更新一次

    async def _schedule_stop(self):
        await asyncio.sleep(self.duration_seconds)
        await self.stop()

    async def stop(self):
        self.status = "converting"  # 更新状态为转换中
        self.end_time = datetime.now()
        
        print(f"停止录制任务，当前状态: {self.status}")
        
        # 停止视频录制
        if self.video_recorder:
            self.video_recorder.stop()
        
        # 停止弹幕抓取
        if self.danmu_client:
            try:
                await self.danmu_client.stop()
            except Exception as e:
                print(f"停止弹幕客户端出错: {e}")
        
        # 等待一段时间，确保文件完全写入
        print("等待文件写入完成...")
        await asyncio.sleep(3)  # 增加等待时间
        
        # 确保文件不再被占用（检查文件大小是否稳定）
        if self.video_file and os.path.exists(self.video_file):
            initial_size = 0
            current_size = 0
            stable_count = 0
            
            print(f"检查文件大小稳定性: {self.video_file}")
            # 检查文件大小是否稳定，确保FFmpeg已完全写入文件
            while stable_count < 3:  # 需要连续3次检查大小不变才认为稳定
                await asyncio.sleep(1)
                if os.path.exists(self.video_file):
                    current_size = os.path.getsize(self.video_file)
                    print(f"文件大小检查: {current_size} 字节")
                    if current_size == initial_size:
                        stable_count += 1
                    else:
                        initial_size = current_size
                        stable_count = 0  # 重置计数
                    print(f"文件大小稳定计数: {stable_count}/3")
                else:
                    print(f"视频文件已消失: {self.video_file}")
                    self.status = "stopped"
                    return
            print("文件大小已稳定，准备转换")
        else:
            print(f"视频文件不存在，跳过稳定性检查: {self.video_file}")
        
        # 转换视频格式为MP4
        if self.video_file and os.path.exists(self.video_file):
            print(f"准备转换文件: {self.video_file}")
            await self._convert_to_mp4()
        else:
            print(f"视频文件不存在，无法转换: {self.video_file}")
            self.status = "stopped"
    
    async def _convert_to_mp4(self):
        """将FLV文件转换为MP4格式"""
        if not self.video_file or not os.path.exists(self.video_file):
            print(f"无法转换: 文件不存在或路径无效: {self.video_file}")
            self.status = "stopped"
            return
            
        # 生成MP4文件名
        mp4_file = self.video_file.replace('.flv', '.mp4')
        
        # 使用ffmpeg进行转换，进行适当的编码以确保兼容性
        cmd = [
            Config.FFMPEG_PATH,
            '-i', self.video_file,
            '-c:v', 'libx264',  # 使用H.264视频编码
            '-c:a', 'aac',      # 使用AAC音频编码
            '-strict', 'experimental',
            '-y',  # 覆盖输出文件
            mp4_file
        ]
        
        try:
            print(f"开始转换视频格式: {self.video_file} -> {mp4_file}")
            print(f"FFmpeg命令: {' '.join(cmd)}")
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            # 更新转换进度
            self.convert_progress = 10  # 开始转换
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                print(f"视频格式转换成功: {mp4_file}")
                # 保存原始文件路径，以便删除
                original_file = self.video_file
                # 更新视频文件路径为MP4文件
                self.video_file = mp4_file
                self.convert_progress = 100  # 转换完成
                
                # 删除原始FLV文件
                try:
                    os.remove(original_file)
                    print(f"已删除原始FLV文件: {original_file}")
                except Exception as e:
                    print(f"删除原始FLV文件失败: {e}")
            else:
                print(f"视频格式转换失败: {stderr.decode()}")
                print(f"转换错误详情: {stderr.decode()}")
                print(f"FFmpeg返回码: {process.returncode}")
                # 如果转换失败，仍然保留原始FLV文件路径
                print("使用原始FLV文件作为视频源")
                self.convert_progress = -1  # 表示转换失败
        except Exception as e:
            print(f"视频格式转换出错: {e}")
            import traceback
            traceback.print_exc()
            # 如果转换失败，仍然保留原始FLV文件路径
            print("使用原始FLV文件作为视频源")
            self.convert_progress = -1  # 表示转换失败
        finally:
            self.status = "stopped"  # 最终状态设为stopped

class RecordingManager:
    def __init__(self):
        self.tasks = {}

    def create_task(self, room_id, stream_url=None, duration_seconds=None, output_dir=None):
        task_id = f"{room_id}_{int(time.time())}"
        task = RecordingTask(task_id, room_id, stream_url, duration_seconds, output_dir)
        self.tasks[task_id] = task
        return task

    async def start_task(self, room_id, stream_url=None, duration_seconds=None, output_dir=None):
        task = self.create_task(room_id, stream_url, duration_seconds, output_dir)
        await task.start()
        return task

    async def stop_task(self, task_id):
        if task_id in self.tasks:
            task = self.tasks[task_id]
            await task.stop()
            return task
        return None

    def get_task(self, task_id):
        return self.tasks.get(task_id)

    def get_all_tasks(self):
        return list(self.tasks.values())

    def get_running_tasks(self):
        return [task for task in self.tasks.values() if task.status == "recording"]