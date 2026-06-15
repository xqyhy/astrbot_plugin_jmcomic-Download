"""
小七月的 JMComic 下载插件 🦊
基于 jmcomic 库，提供禁漫天堂本子的下载/查询/搜索功能
"""

import os
import re
import threading
import time
from datetime import datetime, timedelta
from typing import Optional

import jmcomic
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register, StarTools


# 1分钟最多使用次数
MAX_CALLS_PER_MINUTE = 5


@register(
    "astrbot_plugin_jmcomic-Download",
    "小七月",
    "基于 JMComic-Crawler API 的本子下载/查询/搜索插件",
    "v1.1"
)
class JMComicPlugin(Star):
    """
    JMComic 插件 — 主人说下，本狐就下！(๑•̀ㅂ•́)و✧

    命令：
      /jm download <album_id>   — 下载指定ID的本子
      /jm info <album_id>       — 查看本子详情（标题/作者/标签/章节等）
      /jm search <keyword>      — 搜索本子（支持按作品/作者/标签搜索）
    """

    # ── 速率限制 ───────────────────────────────────────
    # {user_id: [timestamp, ...]}
    _rate_limit: dict = {}
    _rate_lock: threading.Lock

    def _check_rate_limit(self, user_id: str) -> Optional[str]:
        """
        检查用户是否超过频率限制。
        返回 None 表示通过，返回字符串表示被拒绝的提示消息。
        """
        now = time.time()
        cutoff = now - 60  # 1分钟前

        with self._rate_lock:
            # 获取该用户的调用记录
            records = self._rate_limit.get(user_id, [])
            # 只保留1分钟内的记录
            records = [t for t in records if t > cutoff]

            if len(records) >= MAX_CALLS_PER_MINUTE:
                wait_seconds = int(60 - (now - records[0]))
                return (
                    f"⏳ 调用太频繁啦！1分钟内只能使用 {MAX_CALLS_PER_MINUTE} 次哦～\n"
                    f"请 {wait_seconds} 秒后再试 (´・ω・`)"
                )

            # 添加当前调用记录
            records.append(now)
            self._rate_limit[user_id] = records

        return None

    def __init__(self, context: Context, config=None):
        super().__init__(context)
        self.config = config or {}
        self.data_dir = StarTools.get_data_dir("astrbot_plugin_jmcomic_download")
        os.makedirs(self.data_dir, exist_ok=True)

        self.download_dir = self.config.get("download_dir") or os.path.join(self.data_dir, "downloads")
        os.makedirs(self.download_dir, exist_ok=True)

        self._base_option = self._build_base_option()

        # ── 速率限制初始化 ────────────────────────────────
        self._rate_lock = threading.Lock()

        self._clean_enabled = bool(self.config.get("auto_clean_enabled", False))
        self._clean_days = int(self.config.get("auto_clean_days", 7))
        self._clean_thread = None

        if self._clean_enabled:
            self._start_cleaner()
            logger.info(
                f"🧹 自动清理已开启: 每隔1小时检查, 删除超过{self._clean_days}天的.zip文件"
            )

    # ── 自动清理相关方法 ─────────────────────────────────
    def _start_cleaner(self):
        def _loop():
            while True:
                try:
                    self._clean_old_files()
                except Exception as e:
                    logger.error(f"自动清理异常: {e}")
                time.sleep(3600)

        self._clean_thread = threading.Thread(target=_loop, daemon=True)
        self._clean_thread.start()

    def _clean_old_files(self):
        if not os.path.isdir(self.download_dir):
            return

        now = datetime.now()
        cutoff = now - timedelta(days=self._clean_days)
        cleaned = 0

        for fname in os.listdir(self.download_dir):
            if not fname.endswith(".zip"):
                continue
            fpath = os.path.join(self.download_dir, fname)
            if not os.path.isfile(fpath):
                continue

            mtime = datetime.fromtimestamp(os.path.getmtime(fpath))
            if mtime < cutoff:
                os.remove(fpath)
                cleaned += 1
                logger.info(f"🧹 已清理过期压缩包: {fname} (修改时间: {mtime.strftime('%Y-%m-%d %H:%M')})")

        if cleaned > 0:
            logger.info(f"🧹 本次清理完成, 共删除 {cleaned} 个过期压缩包")

    def _build_base_option(self):
        yaml_config = f"""
dir_rule:
  base_dir: {self.download_dir}

download:
  image:
    suffix: .jpg

client:
  impl: api
"""
        return jmcomic.create_option_by_str(yaml_config)

    def _build_download_option(self, album_id: str):
        yaml_config = f"""
dir_rule:
  base_dir: {self.download_dir}

download:
  image:
    suffix: .jpg

client:
  impl: api

plugins:
  after_album:
    - plugin: zip
      kwargs:
        level: album
        delete_original_file: true
        filename_rule: Aid
        suffix: zip
        zip_dir: {self.download_dir}
        encrypt:
          password: {album_id}
"""
        return jmcomic.create_option_by_str(yaml_config)

    def _extract_album_id(self, text: str) -> Optional[str]:
        nums = re.findall(r"\d+", text)
        return nums[0] if nums else None

    def _get_client(self):
        option = self._base_option
        client = option.new_jm_client()
        return client

    # ── 命令: /jm ─────────────────────────────────────
    @filter.command("jm")
    async def jm_command(self, event: AstrMessageEvent, args: str = ""):
        # ── 速率限制检查 ──
        user_id = event.get_sender_id()
        rate_msg = self._check_rate_limit(user_id)
        if rate_msg:
            yield event.plain_result(rate_msg)
            return

        # 优先从纯文本消息中解析，避免 args 丢失
        raw_text = event.get_message_str()
        if raw_text.startswith("/jm"):
            raw_text = raw_text[3:].strip()
        elif raw_text.startswith("jm"):
            raw_text = raw_text[2:].strip()
        else:
            raw_text = args

        parts = raw_text.split(maxsplit=1)
        subcmd = parts[0].lower() if parts else ""
        param = parts[1] if len(parts) > 1 else ""

        if not subcmd:
            yield event.plain_result(
                "用法:\n"
                "  /jm info <album_id>   — 查看本子详情\n"
                "  /jm download <album_id> — 下载本子\n"
                "  /jm search <keyword>  — 搜索本子\n"
                "  /jm help              — 查看帮助"
            )
            return

        if subcmd == "help":
            yield event.plain_result(
                "🦊 JMComic 插件帮助:\n"
                "  /jm info <album_id>   — 查询本子详情\n"
                "  /jm download <album_id> — 下载本子到服务器\n"
                "  /jm search <keyword>  — 搜索本子\n"
                "  /jm help              — 本帮助"
            )
        elif subcmd == "info":
            if not param:
                yield event.plain_result("❌ 请提供本子ID，例如: /jm info 350234")
                return
            async for ret in self._handle_info(event, param):
                yield ret
        elif subcmd == "search":
            if not param:
                yield event.plain_result("❌ 请提供搜索关键词，例如: /jm search 火影")
                return
            async for ret in self._handle_search(event, param):
                yield ret
        elif subcmd == "download":
            if not param:
                yield event.plain_result("❌ 请提供本子ID，例如: /jm download 123")
                return
            async for ret in self._handle_download(event, param):
                yield ret
        else:
            yield event.plain_result(f"❌ 未知子命令: {subcmd}，使用 /jm help 查看帮助")

    # ── 处理 info ──────────────────────────────────────
    async def _handle_info(self, event: AstrMessageEvent, album_id_str: str):
        album_id = self._extract_album_id(album_id_str)
        if not album_id:
            yield event.plain_result("❌ 无法解析本子ID，请输入纯数字ID")
            return

        try:
            yield event.plain_result(f"🔍 正在查询本子 [{album_id}] 的详情，请稍候…")

            client = self._get_client()
            detail = client.get_album_detail(album_id)

            title = detail.title or "未知标题"
            author_list = getattr(detail, "authors", None) or []
            if not author_list:
                author_list = [getattr(detail, "author", "未知")]
            author = ", ".join(author_list)
            tags_str = ", ".join(detail.tags) if detail.tags else "无"

            views = getattr(detail, "views", "?")
            likes = getattr(detail, "likes", "?")
            comments = getattr(detail, "comment_count", "?")

            episodes = ""
            episode_list = getattr(detail, "episode_list", None) or []
            for ep in episode_list:
                if isinstance(ep, tuple) and len(ep) >= 3:
                    ep_id, ep_idx, ep_title = ep[0], ep[1], ep[2] or f"第{ep[1]}话"
                    episodes += f"    {ep_title}  (id: {ep_id})\n"

            msg = (
                f"📖 **{title}**\n"
                f"🆔 ID: JM{detail.id}\n"
                f"✍️ 作者: {author}\n"
                f"👀 观看: {views}  |  ❤️ {likes}  |  💬 {comments}\n"
                f"🏷️ 标签: {tags_str}\n"
            )
            if episodes:
                msg += f"📑 章节 ({len(episode_list)}):\n{episodes}"

            yield event.plain_result(msg)

        except Exception as e:
            logger.error(f"查询本子详情失败: {e}")
            yield event.plain_result(f"❌ 查询失败: {str(e)[:200]}")

    # ── 处理 download ─────────────────────────────────
    async def _handle_download(self, event: AstrMessageEvent, album_id_str: str):
        album_id = self._extract_album_id(album_id_str)
        if not album_id:
            yield event.plain_result("❌ 无法解析本子ID，请输入纯数字ID")
            return

        try:
            yield event.plain_result(f"📥 正在下载本子 [{album_id}]，下载完成后会自动打包加密…")

            option = self._build_download_option(album_id)
            album, dler = jmcomic.download_album(album_id, option)

            zip_path = os.path.join(self.download_dir, f"{album_id}.zip")
            album_title = getattr(album, 'title', album_id)

            yield event.plain_result(
                f"📦 打包完成！正在发送到QQ群…\n"
                f"📖 本子: {album_title}"
            )

            # 发送压缩包到QQ
            try:
                from astrbot.api.message_components import File
                yield event.chain_result([File(
                    name=f"{album_id}.zip",
                    file=zip_path,
                )])
                yield event.plain_result(
                    f"✅ 已发送到QQ群！\n"
                    f"📦 压缩包: {album_id}.zip\n"
                    f"🔑 解压密码: {album_id}"
                )
            except Exception as send_err:
                logger.error(f"发送文件到QQ失败: {send_err}")
                yield event.plain_result(
                    f"❌ 发送到QQ群失败，文件已保存在服务器\n"
                    f"📦 路径: {zip_path}\n"
                    f"🔑 解压密码: {album_id}\n"
                    f"📖 本子: {album_title}\n"
                    f"💡 请管理员从服务器手动获取文件"
                )

        except Exception as e:
            logger.error(f"下载本子失败: {e}")
            yield event.plain_result(f"❌ 下载失败: {str(e)[:200]}")

    # ── 处理 search (使用 JmApiClient.search_album) ────────────────────
    async def _handle_search(self, event: AstrMessageEvent, keyword: str):
        if not keyword.strip():
            yield event.plain_result("❌ 请提供搜索关键词")
            return

        try:
            yield event.plain_result(f"🔎 正在搜索「{keyword}」…")

            client = self._get_client()

            # 调用搜索接口
            # 参数说明：query, page, main_tag, order_by, time, category, sub_category
            search_result = client.search(
                keyword,
                1,      # page
                0,      # main_tag
                'mr',   # order_by: mr=最受欢迎
                'a',    # time: a=全部时间
                '0',    # category: 0=全部
                None,   # sub_category
            )

            # 搜索结果在 content 属性中，格式为 [(id, info_dict), ...]
            raw_albums = getattr(search_result, 'content', None) or []

            if not raw_albums:
                yield event.plain_result(f"😿 没有找到「{keyword}」相关的本子")
                return

            msg = f"🔎 搜索「{keyword}」找到 {len(raw_albums)} 个结果:\n\n"
            for i, item in enumerate(raw_albums[:10], 1):
                if isinstance(item, tuple) and len(item) == 2:
                    aid, info = item
                    title = info.get('name', '未知标题') if isinstance(info, dict) else '未知'
                    author = info.get('author', '?') if isinstance(info, dict) else '?'
                    msg += f"{i}. JM{aid} - {title}\n"
                    msg += f"   ✍️ {author}\n\n"

            msg += "💡 使用 /jm info <ID> 查看详情"
            yield event.plain_result(msg)

        except Exception as e:
            logger.error(f"搜索失败: {e}", exc_info=True)
            yield event.plain_result(
                f"❌ 搜索失败: {str(e)[:200]}\n\n"
                "建议：\n"
                "1. 升级 jmcomic 库：pip install --upgrade jmcomic\n"
                "2. 确保网络可以访问禁漫天堂\n"
                "3. 如果问题依旧，请在配置中添加 cookie（搜索可能需要登录态）"
            )