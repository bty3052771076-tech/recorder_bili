import os
import shutil

class Config:
    # 输出目录
    OUTPUT_DIR = "outputs"
    
    # FFmpeg路径 - 按顺序尝试多个可能的位置
    FFMPEG_PATH = "D:\\ffmpeg\\ffmpeg-8.0-essentials_build\\bin\\ffmpeg.exe"
    
    # B站API相关配置
    BILIBILI_API_HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Referer': 'https://www.bilibili.com/'
    }