import requests
import json
import re

def get_bilibili_stream_url(room_id):
    """
    获取B站直播间的真实流地址
    注意：B站的接口可能会变化，需要根据实际抓包结果进行调整
    """
    try:
        # 设置请求头
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Referer': f'https://live.bilibili.com/{room_id}'
        }
        
        # 先尝试通过网页获取直播间信息
        room_url = f"https://live.bilibili.com/{room_id}"
        room_response = requests.get(room_url, headers=headers)
        room_content = room_response.text
        
        # 从网页内容中提取直播间信息
        # 查找roomInitRes和playurl数据
        import re
        room_info_match = re.search(r'window\.__NEPTUNE_IS_MY_WAIFU__\s*=\s*({.*?});', room_content)
        if room_info_match:
            import json
            room_info = json.loads(room_info_match.group(1))
            room_init_data = room_info.get('roomInitRes', {})
            
            if room_init_data.get('code') == 0:
                real_room_id = room_init_data['data']['room_id']
                
                # 使用新的API获取流地址
                stream_api_url = f"https://api.live.bilibili.com/xlive/web-room/v2/index/getRoomPlayInfo?room_id={real_room_id}&protocol=0,1&format=0,1,2&codec=0,1&qn=10000&platform=web&ptype=8&dolby=5&panorama=1"
                stream_response = requests.get(stream_api_url, headers=headers)
                stream_data = stream_response.json()
                
                if stream_data.get('code') == 0:
                    play_info = stream_data.get('data', {}).get('playurl_info', {}).get('playurl', {})
                    if play_info:
                        # 获取流地址列表
                        streams = play_info.get('stream', [])
                        for stream in streams:
                            if stream.get('protocol_name') == 'http_hls':
                                # 优先选择HTTP HLS流
                                format_list = stream.get('format', [])
                                for fmt in format_list:
                                    if fmt.get('format_name') == 'm3u8':
                                        codec_list = fmt.get('codec', [])
                                        if codec_list:
                                            # 返回第一个可用的URL
                                            url_info = codec_list[0].get('url_info', [])
                                            base_url = codec_list[0].get('base_url', '')
                                            if url_info and base_url:
                                                host = url_info[0].get('host', '')
                                                extra = url_info[0].get('extra', '')
                                                return f"{host}{base_url}{extra}"
                                            
                        # 如果没有找到HLS流，则选择其他流
                        for stream in streams:
                            format_list = stream.get('format', [])
                            for fmt in format_list:
                                codec_list = fmt.get('codec', [])
                                if codec_list:
                                    url_info = codec_list[0].get('url_info', [])
                                    base_url = codec_list[0].get('base_url', '')
                                    if url_info and base_url:
                                        host = url_info[0].get('host', '')
                                        extra = url_info[0].get('extra', '')
                                        return f"{host}{base_url}{extra}"
        else:
            # 回退到旧的API方法
            print("无法从网页内容中提取直播间信息，回退到旧的API方法")
            api_url = f"https://api.live.bilibili.com/room/v1/Room/get_info?room_id={room_id}"
            response = requests.get(api_url, headers=headers)
            data = response.json()
            
            if data['code'] == 0:
                # 获取房间真实ID
                real_room_id = data['data']['room_id']
                
                # 获取流地址
                stream_api_url = f"https://api.live.bilibili.com/room/v1/Room/playUrl?cid={real_room_id}&qn=10000&platform=web"
                stream_response = requests.get(stream_api_url, headers=headers)
                stream_data = stream_response.json()
                
                if stream_data['code'] == 0 and stream_data['data']['durl']:
                    # 返回第一个流地址
                    return stream_data['data']['durl'][0]['url']
                    
    except Exception as e:
        print(f"获取直播间 {room_id} 流地址失败: {e}")
        return None
        
    return None