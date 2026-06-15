# 🦊 astrbot_plugin_jmcomic-Download

基于 [JMComic-Crawler-Python](https://github.com/hect0x7/JMComic-Crawler-Python) API 的 AstrBot 插件。
提供禁漫天堂本子的查询、下载、搜索功能。

**下载流程：** 下载散图 → 拼接长图 → 加密打包为 ZIP → 发送到 QQ 群

## ✨ 功能

| 命令 | 说明 |
|:---|:---|
| `/jm info <album_id>` | 查询本子详情（转发消息格式） |
| `/jm download <album_id>` | 下载本子（散图→长图→加密ZIP→发送到QQ） |
| `/jm search <keyword>` | 搜索本子 |
| `/jm push [关键词]` | 立即推送本子到预设群（不填则用配置/随机） |
| `/jm help` | 查看帮助 |

### 下载流程
```
📥 下载散图 → 🖼️ 拼接长图 → 🔐 打包加密ZIP → 📤 发送到QQ群
                                                   └─ ❌ 失败则提示
```

## 📦 安装

依赖库（已内置在 requirements.txt 中）：
```bash
pip install jmcomic -U
pip install pyzipper
```

将本插件文件夹放入 `AstrBot/data/plugins/` 目录，重启 AstrBot 即可。

## ⚙️ 配置

在 AstrBot 管理面板中可配置：

| 配置项 | 类型 | 默认值 | 说明 |
|:---|:---:|:---|:---|
| `download_dir` | string | 插件数据目录/downloads | 本子下载保存路径 |
| `auto_clean_enabled` | bool | false | 是否开启自动清理旧压缩包 |
| `auto_clean_days` | int | 7 | 文件保留天数 |
| `rate_limit_enabled` | bool | true | 是否开启1分钟使用次数限制 |
| `rate_limit_max_calls` | int | 5 | 每分钟最大调用次数 |
| `push_enabled` | bool | false | 是否开启每日定时推送 |
| `push_cron` | string | "20:00" | 定时推送时间（HH:MM） |
| `push_keywords` | list | [] | 推送关键词列表 |
| `push_group_ids` | list | [] | 推送目标群号列表 |
| `push_random_fallback` | bool | true | 关键词为空时是否随机回退 |

## 📖 使用示例

```
/jm info 350234
→ 转发消息展示本子 JM350234 的详情

/jm download 123
→ 下载→生成长图→加密打包→发送ZIP到QQ，密码=123

/jm search 克苏鲁
→ 搜索标题/作者/标签包含"克苏鲁"的本子

/jm push 全彩
→ 立即用关键词"全彩"搜索并推送到预设群

/jm push
→ 使用配置或随机关键词推送
```

## 🔗 相关链接

- [JMComic-Crawler-Python](https://github.com/hect0x7/JMComic-Crawler-Python)
- [jmcomic 文档](https://jmcomic.readthedocs.io/zh-cn/latest)
