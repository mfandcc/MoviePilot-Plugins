import requests
from app.core.config import settings
from app.log import logger
from datetime import datetime


class EmbySkipHelper:
    """Emby 片头片尾跳过助手类，封装 Emby API 操作"""

    def __init__(self, host: str = None, api_key: str = None):
        """初始化 Emby 助手
        
        Args:
            host: Emby 服务器地址
            api_key: Emby API 密钥
        """
        self.base_url = None
        self.api_key = None
        self.headers = {}
        
        if host or api_key:
            self.set_emby_server(host, api_key)

    def set_emby_server(self, host: str = None, api_key: str = None):
        """配置 Emby 服务器信息
        
        Args:
            host: Emby 服务器地址
            api_key: Emby API 密钥
        """
        # fallback to settings if not provided
        if not host:
            host = settings.EMBY_HOST
        if not api_key:
            api_key = settings.EMBY_API_KEY

        self.base_url = host
        self.api_key = api_key

        if self.base_url is None:
            logger.error('请配置 Emby host (base_url)')
            return

        # Normalize
        if not self.base_url.endswith("/"):
            self.base_url += "/"
        if not self.base_url.startswith("http"):
            self.base_url = "http://" + self.base_url

        self.headers = {'X-Emby-Token': self.api_key} if self.api_key else {}

    @staticmethod
    def format_time(seconds):
        """将秒数转换为时:分:秒.毫秒格式"""
        delta = datetime.utcfromtimestamp(seconds) - datetime.utcfromtimestamp(0)
        formatted_time = str(delta).split(".")[0] + "." + str(delta.microseconds).zfill(6)[:3]
        return formatted_time

    def get_next_episode_ids(self, item_id, season_id, episode_id) -> list:
        """获取下一集的 ID 列表"""
        try:
            ids = []
            response = requests.get(f'{self.base_url}Shows/{item_id}/Episodes', headers=self.headers)
            episodes_info = response.json()
            # 查找下一集的 ID
            for idx, episode in enumerate(episodes_info['Items']):
                if episode['IndexNumber'] >= episode_id and season_id == episode['ParentIndexNumber']:
                    next_episode_item_id = episode['Id']
                    logger.debug(f'第{episode_id + idx}集的 item_ID 为: {next_episode_item_id}')
                    ids.append(next_episode_item_id)
            return ids
        except Exception as e:
            logger.error("异常错误：%s" % str(e))
            return []

    def get_current_video_item_id(self, item_id, season_id, episode_id):
        """获取当前视频的 item ID"""
        try:
            response = requests.get(f'{self.base_url}Shows/{item_id}/Episodes', headers=self.headers)
            episodes_info = response.json()
            # 查找当前集的 ID
            for episode in episodes_info['Items']:
                if episode['IndexNumber'] == episode_id and episode['ParentIndexNumber'] == season_id:
                    item_id = episode['Id']
                    logger.debug(f'第{episode_id}集的 item_ID 为: {item_id}')
                    return item_id
            return -1
        except Exception as e:
            logger.error("异常错误：%s" % str(e))
            return -1

    def update_intro(self, item_id, intro_end):
        """更新片头章节信息"""
        try:
            # 每次先移除旧的introskip
            chapter_info = requests.get(f"{self.base_url}emby/chapter_api/get_chapters?id={item_id}",
                                        headers=self.headers).json()
            old_tags = [chapter['Index'] for chapter in chapter_info['chapters'] if
                        chapter['MarkerType'].startswith('Intro')]
            # 删除旧的
            requests.get(
                f"{self.base_url}emby/chapter_api/update_chapters?id={item_id}&index_list={','.join(map(str, old_tags))}&action=remove",
                headers=self.headers)
            # 添加新的片头开始
            requests.get(
                f"{self.base_url}emby/chapter_api/update_chapters?id={item_id}&action=add&name=%E7%89%87%E5%A4%B4&type=intro_start&time=00:00:00.000",
                headers=self.headers)
            # 新的片头结束
            requests.get(
                f"{self.base_url}emby/chapter_api/update_chapters?id={item_id}&action=add&name=%E7%89%87%E5%A4%B4%E7%BB%93%E6%9D%9F&type=intro_end&time={self.format_time(intro_end)}",
                headers=self.headers)
            return intro_end
        except Exception as e:
            logger.error("异常错误：%s" % str(e))
            return None

    def update_credits(self, item_id, credits_start):
        """更新片尾章节信息"""
        try:
            chapter_info = requests.get(f"{self.base_url}emby/chapter_api/get_chapters?id={item_id}",
                                        headers=self.headers).json()
            old_tags = [chapter['Index'] for chapter in chapter_info['chapters'] if
                        chapter['MarkerType'].startswith('Credits')]
            # 删除旧的
            requests.get(
                f"{self.base_url}emby/chapter_api/update_chapters?id={item_id}&index_list={','.join(map(str, old_tags))}&action=remove",
                headers=self.headers)

            # 添加新的片尾开始
            requests.get(
                f"{self.base_url}emby/chapter_api/update_chapters?id={item_id}&action=add&name=%E7%89%87%E5%B0%BE&type=credits_start&time={self.format_time(credits_start)}",
                headers=self.headers)
            return credits_start
        except Exception as e:
            logger.error("异常错误：%s" % str(e))
            return None

    def get_total_time(self, item_id):
        """获取视频总时长（秒）"""
        try:
            # Some Emby endpoints accept api_key as query param; prefer using header token when available
            url = f'{self.base_url}emby/Items/{item_id}/PlaybackInfo'
            params = {}
            req_headers = self.headers or {}
            if self.api_key:
                # include api key as query param for endpoints that require it
                params['api_key'] = self.api_key
            response = requests.get(url, headers=req_headers, params=params)
            video_info = response.json()
            if video_info['MediaSources']:
                video_info = video_info['MediaSources'][0]
                total_time_ticks = video_info['RunTimeTicks']
                total_time_seconds = total_time_ticks / 10000000  # 将 ticks 转换为秒
                # logger.info(f"{video_info['Name']} 总时长为{total_time_seconds}秒")
                return total_time_seconds
            else:
                logger.error("无法获取视频总时长")
                return 0
        except Exception as e:
            logger.error("异常错误：%s" % str(e))
            return 0


def include_keyword(path: str, keywords: str) -> dict:
    keyword_list: list = keywords.split(',')
    flag = False
    msg = ""
    for keyword in keyword_list:
        if keyword in path:
            flag = True
            msg = keyword
            break
    if flag:
        return {'ret': True, 'msg': msg}
    else:
        return {'ret': False, 'msg': ''}


def exclude_keyword(path: str, keywords: str) -> dict:
    keyword_list: list = keywords.split(',') if keywords else []
    for keyword in keyword_list:
        if keyword in path:
            return {'ret': False, 'msg': keyword}
    return {'ret': True, 'msg': ''}


if __name__ == '__main__':
    # 测试代码示例
    helper = EmbySkipHelper()
    # print(*helper.get_next_episode_ids(5842, 2, 2))
    # print(helper.get_total_time(1847))
