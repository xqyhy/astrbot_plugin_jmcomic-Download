"""
小七月的 JMComic 下载插件 🦊
基于 jmcomic 库，提供禁漫天堂本子的下载/查询/搜索功能
下载散图 → 拼接长图 → 加密打包长图为 ZIP
发送一条消息包含文本说明 + 压缩包文件
新增定时推送（默认关闭）、立即推送指令
修复主动消息发送：直接传递群号字符串
"""

import os
import re
import threading
import time
import asyncio
import random
import zipfile
import shutil
from datetime import datetime, timedelta
from typing import Optional, List

import jmcomic
from jmcomic import Feature
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter, MessageChain
from astrbot.api.star import Context, Star, register, StarTools
from astrbot.api.message_components import Plain, File

# 尝试导入加密压缩库
try:
    import pyzipper
    HAS_PYZIPPER = True
except ImportError:
    HAS_PYZIPPER = False
    logger.warning("⚠️ 未安装 pyzipper，将使用无加密 ZIP 压缩（不推荐）。建议运行: pip install pyzipper")

# 1分钟最多使用次数
MAX_CALLS_PER_MINUTE = 5
DEFAULT_RANDOM_KEYWORDS = ["全彩", "汉化", "单行本", "新作", "热门"]


@register(
    "astrbot_plugin_jmcomic-Download",
    "小七月",
    "基于 JMComic-Crawler API 的本子下载/查询/搜索插件 (长图加密压缩、定时推送)",
    "v2.5"
)
class JMComicPlugin(Star):
    """
    JMComic 插件 — 主人说下，本狐就下！(๑•̀ㅂ•́)و✧

    命令：
      /jm download <album_id>   — 下载本子（散图→长图→加密ZIP）
      /jm info <album_id>       — 查看本子详情
      /jm search <keyword>      — 搜索本子
      /jm push [关键词]          — 立即推送本子（不填则使用配置/随机）
      /jm help                  — 查看帮助
    """

    _rate_limit: dict = {}
    _rate_lock: threading.Lock

    def _check_rate_limit(self, user_id: str) -> Optional[str]:
        now = time.time()
        cutoff = now - 60
        with self._rate_lock:
            records = self._rate_limit.get(user_id, [])
            records = [t for t in records if t > cutoff]
            if len(records) >= MAX_CALLS_PER_MINUTE:
                wait_seconds = int(records[0] + 60 - now)
                return f"⏳ 调用太频繁啦！1分钟内只能使用 {MAX_CALLS_PER_MINUTE} 次哦～\n请 {wait_seconds} 秒后再试 (´・ω・`)"
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

        self._rate_lock = threading.Lock()
        self._clean_enabled = bool(self.config.get("auto_clean_enabled", False))
        self._clean_days = int(self.config.get("auto_clean_days", 7))
        self._clean_thread = None
        if self._clean_enabled:
            self._start_cleaner()
            logger.info(f"🧹 自动清理已开启: 每隔1小时检查, 删除超过{self._clean_days}天的.zip文件")

        # 推送配置
        self.push_enabled = bool(self.config.get("push_enabled", False))
        self.push_cron = self.config.get("push_cron", "20:00")
        self.push_keywords: List[str] = self.config.get("push_keywords", [])
        self.push_group_ids: List[int] = self.config.get("push_group_ids", [])
        self.push_random_fallback = bool(self.config.get("push_random_fallback", True))

        if self.push_enabled and self.push_group_ids:
            self.loop = asyncio.get_event_loop()
            self.push_task = self.loop.create_task(self._push_scheduler())
            logger.info(f"⏰ 定时推送已启动，每日 {self.push_cron} 执行，目标群: {self.push_group_ids}")
        elif self.push_enabled:
            logger.warning("⚠️ 定时推送已启用但未配置 push_group_ids，不会执行推送")

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
                logger.info(f"🧹 已清理过期压缩包: {fname}")
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
        # 只下载，不自动打包（手动打包长图）
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

    def _extract_album_id(self, text: str) -> Optional[str]:
        nums = re.findall(r"\d+", text)
        return nums[0] if nums else None

    def _get_client(self):
        return self._build_base_option().new_jm_client()

    # 推送方法
    def _get_random_keyword(self) -> str:
        return random.choice(DEFAULT_RANDOM_KEYWORDS)

    async def _get_push_content(self, keyword: Optional[str] = None) -> str:
        if keyword:
            final_keyword = keyword.strip()
        else:
            if self.push_keywords:
                final_keyword = random.choice(self.push_keywords)
            elif self.push_random_fallback:
                final_keyword = self._get_random_keyword()
            else:
                return "❌ 未配置推送关键词且不允许随机回退，无法推送。"
        try:
            client = self._get_client()
            search_result = client.search(final_keyword, 1, 0, 'mr', 'a', '0', None)
            if hasattr(search_result, 'content'):
                raw_albums = search_result.content
            elif isinstance(search_result, list):
                raw_albums = search_result
            else:
                raw_albums = []
            if not raw_albums:
                return f"😿 没有找到与「{final_keyword}」相关的本子"
            msg = f"🔔 今日推送 — 关键词「{final_keyword}」\n找到 {len(raw_albums)} 个结果，随机展示前5个：\n\n"
            for i, item in enumerate(raw_albums[:5], 1):
                if isinstance(item, tuple) and len(item) == 2:
                    aid, info = item
                    title = info.get('name', '未知标题') if isinstance(info, dict) else '未知'
                    author = info.get('author', '?') if isinstance(info, dict) else '?'
                    msg += f"{i}. JM{aid} - {title}\n   ✍️ {author}\n\n"
            msg += "💡 使用 /jm info <ID> 查看详情，/jm download <ID> 下载本子"
            return msg
        except Exception as e:
            logger.error(f"获取推送内容失败: {e}")
            return f"❌ 推送内容生成失败: {str(e)[:200]}"

    def _get_platform_id(self) -> str:
        """
        从 context 自动获取当前 AIOCQHTTP (QQ) 平台的 ID。
        这样无论用户把平台 ID 设置成什么，都能动态适配。
        """
        for platform in self.context.platform_manager.platform_insts:
            if platform.meta().name == "aiocqhttp":
                return platform.meta().id
        return ""

    async def _send_to_group(self, group_id: int, message: str):
        """
        发送主动消息到指定群
        使用 UMO 格式: platform_id:GroupMessage:群号
        """
        try:
            chain = MessageChain().message(message)
            platform_id = self._get_platform_id()
            session = f"{platform_id}:GroupMessage:{group_id}"
            await self.context.send_message(session, chain)
            logger.debug(f"成功发送消息到群 {group_id}")
        except Exception as e:
            logger.error(f"发送消息到群 {group_id} 失败: {e}")

    async def _do_push(self, keyword: Optional[str] = None) -> str:
        if not self.push_group_ids:
            return "❌ 未配置推送目标群 (push_group_ids)"
        content = await self._get_push_content(keyword)
        success_count = 0
        for gid in self.push_group_ids:
            await self._send_to_group(gid, content)
            success_count += 1
            await asyncio.sleep(0.5)
        return f"✅ 已向 {success_count} 个群发送推送消息。\n\n{content}"

    async def _push_scheduler(self):
        while True:
            try:
                now = datetime.now()
                target_hour, target_min = map(int, self.push_cron.split(':'))
                target_time = now.replace(hour=target_hour, minute=target_min, second=0, microsecond=0)
                if target_time <= now:
                    target_time += timedelta(days=1)
                wait_seconds = (target_time - now).total_seconds()
                logger.info(f"📅 下次定时推送时间: {target_time.strftime('%Y-%m-%d %H:%M:%S')} (等待 {wait_seconds/3600:.1f} 小时)")
                await asyncio.sleep(wait_seconds)
                logger.info("⏰ 定时推送触发")
                await self._do_push()
            except Exception as e:
                logger.error(f"定时推送循环出错: {e}")
                await asyncio.sleep(60)

    @filter.command("jm")
    async def jm_command(self, event: AstrMessageEvent, args: str = ""):
        user_id = event.get_sender_id()
        rate_msg = self._check_rate_limit(user_id)
        if rate_msg:
            yield event.plain_result(rate_msg)
            return

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
                "  /jm info <album_id>     — 查看本子详情\n"
                "  /jm download <album_id> — 下载本子（散图→长图→加密ZIP）\n"
                "  /jm search <keyword>    — 搜索本子\n"
                "  /jm push [关键词]        — 立即推送本子到预设群\n"
                "  /jm help                — 查看帮助"
            )
            return

        if subcmd == "help":
            yield event.plain_result(
                "🦊 JMComic 插件帮助:\n"
                "  /jm info <album_id>     — 查询本子详情\n"
                "  /jm download <album_id> — 下载本子（自动生成长图并打包加密ZIP）\n"
                "  /jm search <keyword>    — 搜索本子\n"
                "  /jm push [关键词]        — 立即推送本子到预设群（不填则用配置/随机）\n"
                "  /jm help                — 本帮助"
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
        elif subcmd in ("push", "pushnow"):
            keyword = param if param else None
            result = await self._do_push(keyword)
            yield event.plain_result(result)
        else:
            yield event.plain_result(f"❌ 未知子命令: {subcmd}，使用 /jm help 查看帮助")

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
            basic_info = (
                f"📖 标题：{title}\n"
                f"🆔 ID：JM{detail.id}\n"
                f"✍️ 作者：{author}\n"
                f"👀 观看：{views}  |  ❤️ {likes}  |  💬 {comments}\n"
                f"🏷️ 标签：{tags_str}"
            )
            episodes_block = ""
            episode_list = getattr(detail, "episode_list", None) or []
            if episode_list:
                episodes_lines = []
                for ep in episode_list:
                    if isinstance(ep, tuple) and len(ep) >= 3:
                        ep_id, ep_idx, ep_title = ep[0], ep[1], ep[2] or f"第{ep[1]}话"
                        episodes_lines.append(f"  • {ep_title} (id: {ep_id})")
                episodes_block = f"📑 章节 ({len(episode_list)}):\n" + "\n".join(episodes_lines)
            msg = basic_info
            if episodes_block:
                msg += "\n\n" + episodes_block
            msg += "\n\n💡 使用 /jm download <ID> 下载本子\n💡 使用 /jm search <关键词> 搜索更多"
            yield event.plain_result(msg)
        except Exception as e:
            logger.error(f"查询本子详情失败: {e}")
            yield event.plain_result(f"❌ 查询失败: {str(e)[:200]}")

    async def _handle_download(self, event: AstrMessageEvent, album_id_str: str):
        album_id = self._extract_album_id(album_id_str)
        if not album_id:
            yield event.plain_result("❌ 无法解析本子ID，请输入纯数字ID")
            return

        try:
            yield event.plain_result(f"📥 正在下载本子 [{album_id}]，下载完成后会生成长图并加密打包…")

            option = self._build_download_option(album_id)
            # 启用长图导出
            album, dler = jmcomic.download_album(album_id, option, extra=Feature.export_long_img)

            album_title = getattr(album, 'title', album_id)
            safe_title = re.sub(r'[\\/*?:"<>|]', '', album_title)
            long_img_name = f"[JM{album_id}]{safe_title}.png"
            long_img_path = os.path.join(self.download_dir, long_img_name)

            if not os.path.exists(long_img_path):
                raise Exception("长图生成失败，请检查 jmcomic 版本及 Pillow 库")

            # 打包长图为加密 ZIP
            zip_path = os.path.join(self.download_dir, f"{album_id}.zip")
            if HAS_PYZIPPER:
                with pyzipper.AESZipFile(zip_path, 'w', compression=pyzipper.ZIP_DEFLATED, encryption=pyzipper.WZ_AES) as zf:
                    zf.setpassword(album_id.encode())
                    zf.write(long_img_path, arcname=long_img_name)
                logger.info(f"✅ 已生成加密压缩包: {zip_path} (密码: {album_id})")
            else:
                # 无加密回退
                with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                    zf.write(long_img_path, arcname=long_img_name)
                logger.warning(f"⚠️ 未安装 pyzipper，压缩包无加密: {zip_path}")

            # 删除长图原始文件（已打包）
            os.remove(long_img_path)

            # 清理原始散图目录
            album_dir = os.path.join(self.download_dir, f"JM{album_id}")
            if os.path.isdir(album_dir):
                shutil.rmtree(album_dir)
                logger.info(f"🗑️ 已清理散图目录: {album_dir}")

            # 获取压缩包大小
            zip_size_mb = os.path.getsize(zip_path) // (1024 * 1024)

            # 构建文本说明
            message_text = (
                f"📖 本子：{album_title}\n"
                f"🆔 ID：JM{album_id}\n"
                f"🔒 解压密码：{album_id}\n"
                f"📦 压缩包：{album_id}.zip\n"
                f"💾 大小：{zip_size_mb} MB\n"
                f"🖼️ 内容：整本拼接长图"
            )

            # 发送一条消息：文本 + 文件
            yield event.chain_result([
                Plain(message_text),
                File(name=f"{album_id}.zip", file=zip_path)
            ])

        except Exception as e:
            logger.error(f"下载本子失败: {e}")
            yield event.plain_result(f"❌ 下载失败: {str(e)[:200]}")

    async def _handle_search(self, event: AstrMessageEvent, keyword: str):
        if not keyword.strip():
            yield event.plain_result("❌ 请提供搜索关键词")
            return
        try:
            yield event.plain_result(f"🔎 正在搜索「{keyword}」…")
            client = self._get_client()
            search_result = client.search(keyword, 1, 0, 'mr', 'a', '0', None)
            if hasattr(search_result, 'content'):
                raw_albums = search_result.content
            elif isinstance(search_result, list):
                raw_albums = search_result
            else:
                raw_albums = []
            if not raw_albums:
                yield event.plain_result(f"😿 没有找到「{keyword}」相关的本子")
                return
            msg = f"🔎 搜索「{keyword}」找到 {len(raw_albums)} 个结果:\n\n"
            for i, item in enumerate(raw_albums[:10], 1):
                if isinstance(item, tuple) and len(item) == 2:
                    aid, info = item
                    title = info.get('name', '未知标题') if isinstance(info, dict) else '未知'
                    author = info.get('author', '?') if isinstance(info, dict) else '?'
                    msg += f"{i}. JM{aid} - {title}\n   ✍️ {author}\n\n"
            msg += "💡 使用 /jm info <ID> 查看详情"
            yield event.plain_result(msg)
        except Exception as e:
            logger.error(f"搜索失败: {e}", exc_info=True)
            yield event.plain_result(f"❌ 搜索失败: {str(e)[:200]}\n\n建议：\n1. 升级 jmcomic 库：pip install --upgrade jmcomic\n2. 确保网络可以访问禁漫天堂\n3. 如果问题依旧，请在配置中添加 cookie")