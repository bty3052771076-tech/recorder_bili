import asyncio
import json
import time
import struct
import zlib
import aiofiles
import websockets
import threading

class DanmuClient:
    def __init__(self, room_id, output_file):
        self.room_id = room_id
        self.output_file = output_file
        self.ws = None
        self.heartbeat_task = None
        self.running = False
        self.heartbeat_interval = 30  # 心跳间隔（秒）
        self.loop = None
        self.websocket_task = None
        
    def start(self):
        self.running = True
        # 在新线程中运行事件循环
        self.thread = threading.Thread(target=self._run_async_loop)
        self.thread.daemon = True
        self.thread.start()
        
    def _run_async_loop(self):
        # 创建新的事件循环
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        # 运行WebSocket连接任务
        self.websocket_task = self.loop.create_task(self._connect())
        self.loop.run_forever()
        
    async def _connect(self):
        # B站弹幕服务器地址
        # 获取服务器地址
        try:
            uri = "wss://broadcastlv.chat.bilibili.com:443/sub"
            # 增加连接超时时间，并设置心跳参数
            async with websockets.connect(
                uri, 
                ping_interval=20, 
                ping_timeout=10, 
                close_timeout=10,
                extra_headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                }
            ) as websocket:
                self.ws = websocket
                # 发送认证包
                await self._send_auth()
                print(f"已连接到直播间 {self.room_id} 的弹幕服务器")
                
                # 启动心跳任务
                self.heartbeat_task = asyncio.create_task(self._send_heartbeat())
                
                # 接收消息
                while self.running:
                    try:
                        message = await asyncio.wait_for(websocket.recv(), timeout=2.0)
                        # 解析接收到的弹幕数据
                        await self._parse_danmu_message(message)
                    except asyncio.TimeoutError:
                        # 超时继续循环
                        continue
                    except websockets.exceptions.ConnectionClosed:
                        print(f"与直播间 {self.room_id} 的WebSocket连接已关闭")
                        break
                    except Exception as e:
                        if self.running:
                            print(f"接收消息出错: {e}")
                        break
        except websockets.exceptions.InvalidStatusCode as e:
            print(f"连接WebSocket出错 (状态码错误): {e}")
        except websockets.exceptions.WebSocketException as e:
            print(f"WebSocket连接出错: {e}")
        except Exception as e:
            print(f"连接WebSocket出错: {e}")
        finally:
            print(f"已断开与直播间 {self.room_id} 的弹幕服务器连接")
            if self.heartbeat_task:
                self.heartbeat_task.cancel()
                
        print(f"弹幕客户端任务结束，直播间 {self.room_id}")
                
    async def _send_auth(self):
        # 创建认证包
        auth_packet = self._create_auth_packet()
        if self.ws:
            await self.ws.send(auth_packet)
        
    def _create_auth_packet(self):
        # 创建认证包
        # 协议说明：
        # 1. 数据包格式：Header(16字节) + Body(JSON)
        # 2. Header包含：数据包总长度(4字节)、头部长度(2字节)、协议版本(2字节)、操作码(4字节)、序列号(4字节)
        # 3. Body包含认证信息
        
        # 认证信息
        auth_info = {
            "uid": 0,
            "roomid": int(self.room_id),
            "protover": 2,  # 协议版本
            "platform": "web",
            "clientver": "1.14.3",
            "type": 2
        }
        
        # 将认证信息转换为JSON并编码
        auth_json = json.dumps(auth_info, ensure_ascii=False)
        auth_bytes = auth_json.encode('utf-8')
        
        # 构建数据包头部
        packet_len = 16 + len(auth_bytes)
        header = struct.pack(
            '>IHHII',  # 大端序
            packet_len,  # 数据包总长度
            16,          # 头部长度
            2,           # 协议版本
            7,           # 操作码(认证包)
            1            # 序列号
        )
        
        # 组合完整数据包
        packet = header + auth_bytes
        return packet
        
    async def _send_heartbeat(self):
        # 定时发送心跳包
        while self.running:
            try:
                # 构建心跳包
                heartbeat_packet = self._create_heartbeat_packet()
                if self.ws and not self.ws.closed:
                    await self.ws.send(heartbeat_packet)
                    print(f"已发送心跳包到直播间 {self.room_id}")
            except Exception as e:
                print(f"发送心跳包出错: {e}")
            
            # 等待下次心跳
            await asyncio.sleep(self.heartbeat_interval)
            
    def _create_heartbeat_packet(self):
        # 创建心跳包
        # 心跳包内容为空，只有头部
        
        # 构建数据包头部
        header = struct.pack(
            '>IHHII',  # 大端序
            16,  # 数据包总长度(只有头部)
            16,  # 头部长度
            1,   # 协议版本
            2,   # 操作码(心跳包)
            1    # 序列号
        )
        
        return header
        
    async def _parse_danmu_message(self, message):
        # 解析弹幕消息
        offset = 0
        while offset < len(message):
            # 解析头部
            if len(message) < offset + 16:
                break
                
            # 解析头部信息
            header = message[offset:offset+16]
            packet_len, header_len, proto_ver, op_code, seq_id = struct.unpack('>IHHII', header)
            
            # 获取数据体
            body = message[offset+header_len:offset+packet_len]
            
            # 根据操作码处理不同类型的包
            if op_code == 5:  # 通知包（弹幕、礼物等）
                if proto_ver == 2:  # 压缩过的数据
                    # 解压数据
                    try:
                        uncompressed_body = zlib.decompress(body)
                        # 递归解析解压后的数据
                        await self._parse_danmu_message(uncompressed_body)
                    except zlib.error as e:
                        print(f"解压数据失败: {e}")
                elif proto_ver == 0:  # 未压缩的数据
                    # 解析JSON数据
                    try:
                        data = json.loads(body.decode('utf-8'))
                        # 保存弹幕数据
                        await self._save_danmu_data(data)
                    except Exception as e:
                        print(f"解析弹幕数据出错: {e}")
            
            # 移动到下一个包
            offset += packet_len
            
    async def _save_danmu_data(self, data):
        # 保存弹幕数据到文件
        # 只保存指定类型的弹幕
        cmd_types = [
            'DANMU_MSG',
            'SUPER_CHAT_MESSAGE',
            'SEND_GIFT',
            'GUARD_BUY',
            'INTERACT_WORD',
            'LIVE',
            'PREPARING'
        ]
        
        if 'cmd' in data and data['cmd'] in cmd_types:
            # 构建保存的数据
            danmu_data = {
                'timestamp': time.time(),
                'room_id': self.room_id,
                'cmd': data['cmd'],
                'raw': data
            }
            
            # 解析特定字段
            if data['cmd'] == 'DANMU_MSG' and 'info' in data:
                danmu_data['username'] = data['info'][2][1] if len(data['info']) > 2 and len(data['info'][2]) > 1 else ''
                danmu_data['content'] = data['info'][1] if len(data['info']) > 1 else ''
            
            elif data['cmd'] == 'SUPER_CHAT_MESSAGE' and 'data' in data:
                sc_data = data['data']
                danmu_data['username'] = sc_data.get('user_info', {}).get('uname', '')
                danmu_data['content'] = sc_data.get('message', '')
                danmu_data['price'] = sc_data.get('price', 0)
                
            elif data['cmd'] == 'SEND_GIFT' and 'data' in data:
                gift_data = data['data']
                danmu_data['username'] = gift_data.get('uname', '')
                danmu_data['gift_name'] = gift_data.get('giftName', '')
                danmu_data['gift_count'] = gift_data.get('num', 0)
                
            elif data['cmd'] == 'GUARD_BUY' and 'data' in data:
                guard_data = data['data']
                danmu_data['username'] = guard_data.get('username', '')
                danmu_data['guard_level'] = guard_data.get('guard_level', 0)
                
            # 写入文件
            try:
                async with aiofiles.open(self.output_file, mode='a', encoding='utf-8') as f:
                    await f.write(json.dumps(danmu_data, ensure_ascii=False) + '\n')
            except Exception as e:
                print(f"保存弹幕数据出错: {e}")
                
    async def stop(self):
        self.running = False
        
        # 取消心跳任务
        if self.heartbeat_task:
            self.heartbeat_task.cancel()
            
        # 关闭WebSocket连接
        if self.ws and not self.ws.closed:
            try:
                await self.ws.close()
            except Exception as e:
                print(f"关闭WebSocket连接出错: {e}")
            
        # 停止事件循环
        if self.loop:
            try:
                self.loop.call_soon_threadsafe(self.loop.stop)
            except Exception as e:
                print(f"停止事件循环出错: {e}")
            
        print(f"已停止抓取直播间 {self.room_id} 的弹幕")