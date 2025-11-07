from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import os
import json
from recorder.manager import RecordingManager
from recorder.config import Config
from pydantic import BaseModel
from typing import Optional

app = FastAPI(title="Bilibili直播录制工具", version="1.0.0")

# 添加CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 在生产环境中应该限制具体的域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载静态文件目录
app.mount("/web", StaticFiles(directory="web"), name="web")
app.mount("/outputs", StaticFiles(directory="outputs"), name="outputs")

# 初始化录制管理器
recording_manager = RecordingManager()

# 请求模型
class StartRecordRequest(BaseModel):
    room_id: str
    custom_stream_url: Optional[str] = None
    duration_seconds: Optional[int] = None
    output_dir: Optional[str] = None

class StopRecordRequest(BaseModel):
    task_id: str

@app.get("/")
async def read_root():
    return FileResponse("web/index.html")

@app.post("/api/record/start")
async def start_record(request: StartRecordRequest):
    try:
        # 如果没有提供自定义流地址，则获取真实的流地址
        stream_url = request.custom_stream_url
        if not stream_url:
            from recorder.utils import get_bilibili_stream_url
            stream_url = get_bilibili_stream_url(request.room_id)
            if not stream_url:
                raise HTTPException(status_code=400, detail="无法获取直播间流地址")
        
        # 启动录制任务
        task = await recording_manager.start_task(
            room_id=request.room_id,
            stream_url=stream_url,
            duration_seconds=request.duration_seconds,
            output_dir=request.output_dir
        )
        
        return {
            "task_id": task.task_id,
            "status": "started",
            "message": "录制任务已启动"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/record/stop")
async def stop_record(request: StopRecordRequest):
    try:
        task = await recording_manager.stop_task(request.task_id)
        if not task:
            raise HTTPException(status_code=404, detail="任务不存在")
            
        return {
            "task_id": task.task_id,
            "status": "stopped",
            "message": "录制任务已停止"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/record/status")
async def get_record_status():
    tasks = recording_manager.get_all_tasks()
    task_list = []
    
    for task in tasks:
        task_info = {
            "task_id": task.task_id,
            "room_id": task.room_id,
            "stream_url": task.stream_url,
            "start_time": task.start_time.isoformat() if task.start_time else None,
            "duration_seconds": task.duration_seconds,
            "video_file": task.video_file,
            "danmaku_file": task.danmaku_file,
            "status": task.status,
            "record_progress": task.record_progress,
            "convert_progress": task.convert_progress,
            "elapsed_time": task.elapsed_time
        }
        task_list.append(task_info)
        
    return task_list

@app.get("/api/recordings")
async def get_recordings():
    recordings = []
    # 使用字典来避免重复的session_id
    session_map = {}
    
    # 遍历输出目录，查找所有录制会话
    if os.path.exists(Config.OUTPUT_DIR):
        for room_id in os.listdir(Config.OUTPUT_DIR):
            room_path = os.path.join(Config.OUTPUT_DIR, room_id)
            if os.path.isdir(room_path):
                # 查找该房间下的所有视频文件
                for file in os.listdir(room_path):
                    if file.endswith((".flv", ".mp4")):
                        # 从视频文件名中提取时间戳
                        if file.endswith(".flv"):
                            base_name = file[:-4]  # 去掉.flv后缀
                        else:  # .mp4
                            base_name = file[:-4]  # 去掉.mp4后缀
                        
                        video_file = os.path.join(room_path, file)
                        
                        # 查找对应的弹幕文件
                        danmaku_file = None
                        danmaku_filename = f"{base_name}_danmaku.jsonl"
                        danmaku_path = os.path.join(room_path, danmaku_filename)
                        if os.path.exists(danmaku_path):
                            danmaku_file = danmaku_path
                        
                        # 从文件名中提取时间戳
                        start_time_str = base_name
                        if "_" in base_name:
                            parts = base_name.split("_")
                            if len(parts) >= 3:
                                start_time_str = f"{parts[-2]}_{parts[-1]}"
                        
                        # 优先选择MP4格式，如果同时存在FLV和MP4
                        session_id = base_name
                        if session_id not in session_map:
                            # 如果session_id不存在，直接添加
                            session_map[session_id] = {
                                "session_id": session_id,
                                "room_id": room_id,
                                "start_time": start_time_str,
                                "video_file": video_file,
                                "danmaku_file": danmaku_file,
                                "is_limited": False  # 简化处理，实际应该从任务信息中获取
                            }
                        else:
                            # 如果session_id已存在，优先选择MP4格式
                            existing_file = session_map[session_id]["video_file"]
                            if file.endswith(".mp4") and existing_file.endswith(".flv"):
                                # 如果当前文件是MP4而现有文件是FLV，替换为MP4
                                session_map[session_id]["video_file"] = video_file
                                if danmaku_file:  # 如果有弹幕文件也更新
                                    session_map[session_id]["danmaku_file"] = danmaku_file
    
    # 将字典的值转换为列表
    recordings = list(session_map.values())
    
    # 按房间号分组并按时间排序
    grouped_recordings = {}
    for recording in recordings:
        room_id = recording["room_id"]
        if room_id not in grouped_recordings:
            grouped_recordings[room_id] = []
        grouped_recordings[room_id].append(recording)
    
    # 对每个房间的录制内容按时间排序（降序）
    for room_id in grouped_recordings:
        grouped_recordings[room_id].sort(key=lambda x: x["start_time"], reverse=True)
    
    return {"grouped": grouped_recordings, "flat": recordings}

@app.get("/api/recordings/{session_id}")
async def get_recording_detail(session_id: str):
    # 查找指定会话的详细信息
    if os.path.exists(Config.OUTPUT_DIR):
        for room_id in os.listdir(Config.OUTPUT_DIR):
            room_path = os.path.join(Config.OUTPUT_DIR, room_id)
            if os.path.isdir(room_path):
                # 直接在房间目录下查找文件
                video_file = None
                danmaku_file = None
                
                # 优先查找MP4文件，如果没有再查找FLV文件
                mp4_file = None
                flv_file = None
                
                for file in os.listdir(room_path):
                    if file.startswith(session_id):
                        if file.endswith(".mp4"):
                            mp4_file = os.path.join(room_path, file)
                        elif file.endswith(".flv"):
                            flv_file = os.path.join(room_path, file)
                
                # 优先使用MP4文件
                if mp4_file:
                    video_file = mp4_file
                elif flv_file:
                    video_file = flv_file
                
                # 查找对应的弹幕文件
                if video_file:
                    danmaku_filename = f"{session_id}_danmaku.jsonl"
                    danmaku_path = os.path.join(room_path, danmaku_filename)
                    if os.path.exists(danmaku_path):
                        danmaku_file = danmaku_path
                    
                    return {
                        "session_id": session_id,
                        "room_id": room_id,
                        "video_file": video_file,
                        "danmaku_file": danmaku_file,
                        "start_time": session_id.split("_")[-2] + "_" + session_id.split("_")[-1] if "_" in session_id else session_id
                    }

    raise HTTPException(status_code=404, detail="录制会话不存在")

@app.get("/danmaku/{room_id}/{filename}")
async def get_danmaku_file(room_id: str, filename: str):
    """获取弹幕文件内容"""
    file_path = os.path.join(Config.OUTPUT_DIR, room_id, filename)
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="弹幕文件不存在")
    
    def iterfile():
        with open(file_path, encoding="utf-8") as f:
            yield from f
    
    return StreamingResponse(iterfile(), media_type="text/plain")

@app.get("/api/danmaku/{room_id}/{filename}")
async def get_danmaku_data(room_id: str, filename: str, limit: int = 100):
    """获取弹幕数据（JSON格式）"""
    file_path = os.path.join(Config.OUTPUT_DIR, room_id, filename)
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="弹幕文件不存在")
    
    danmaku_list = []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
            # 读取最后limit行
            for line in lines[-limit:]:
                try:
                    danmaku_list.append(json.loads(line.strip()))
                except json.JSONDecodeError:
                    continue
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读取弹幕文件出错: {str(e)}")
    
    return danmaku_list

@app.get("/video/{path:path}")
async def get_video_file(path: str, request: Request):
    """获取视频文件，支持Range请求用于流式播放"""
    file_path = os.path.join(Config.OUTPUT_DIR, path)
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="视频文件不存在")
    
    # 获取文件大小
    file_size = os.path.getsize(file_path)
    
    # 根据文件扩展名确定媒体类型
    if file_path.endswith('.mp4'):
        media_type = 'video/mp4'
    elif file_path.endswith('.flv'):
        media_type = 'video/x-flv'
    else:
        media_type = 'video/mp4'  # 默认
    
    # 获取Range请求头
    range_header = request.headers.get('range')
    
    if range_header:
        # 解析Range请求
        bytes_start, bytes_end = range_header.replace('bytes=', '').split('-')
        start = int(bytes_start) if bytes_start else 0
        end = int(bytes_end) if bytes_end else file_size - 1
        
        # 确保end不超过文件大小
        if end >= file_size:
            end = file_size - 1
            
        # 计算chunk大小
        chunk_size = end - start + 1
        
        def iterfile():
            with open(file_path, 'rb') as f:
                f.seek(start)
                remaining = chunk_size
                while remaining > 0:
                    chunk = f.read(min(8192, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    yield chunk
        
        return StreamingResponse(
            iterfile(),
            status_code=206,
            media_type=media_type,
            headers={
                'Content-Range': f'bytes {start}-{end}/{file_size}',
                'Accept-Ranges': 'bytes',
                'Content-Length': str(chunk_size)
            }
        )
    else:
        # 非Range请求，返回整个文件
        def iterfile():
            with open(file_path, 'rb') as f:
                yield from f
        
        return StreamingResponse(
            iterfile(),
            media_type=media_type,
            headers={
                'Content-Length': str(file_size),
                'Accept-Ranges': 'bytes'
            }
        )

@app.delete("/api/recordings/{session_id}")
async def delete_recording(session_id: str):
    """删除指定的录制文件"""
    try:
        # 遍历输出目录，查找匹配的会话
        if os.path.exists(Config.OUTPUT_DIR):
            for room_id in os.listdir(Config.OUTPUT_DIR):
                room_path = os.path.join(Config.OUTPUT_DIR, room_id)
                if os.path.isdir(room_path):
                    # 查找匹配session_id的文件
                    for file in os.listdir(room_path):
                        if file.startswith(session_id):
                            file_path = os.path.join(room_path, file)
                            if os.path.isfile(file_path):
                                os.remove(file_path)
                                print(f"已删除文件: {file_path}")
                    
                    # 检查房间目录是否为空，如果是则删除目录
                    if os.path.isdir(room_path) and not os.listdir(room_path):
                        os.rmdir(room_path)
                        print(f"已删除空房间目录: {room_path}")
        
        return {"message": "删除成功", "session_id": session_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除失败: {str(e)}")

@app.on_event('startup')
def startup_event():
    # 确保输出目录存在
    os.makedirs(Config.OUTPUT_DIR, exist_ok=True)

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)