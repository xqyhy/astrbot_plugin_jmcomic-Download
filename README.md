# 🦊 astrbot_plugin_jmcomic-Download

基于 [JMComic-Crawler-Python](https://github.com/hect0x7/JMComic-Crawler-Python) API 的 AstrBot 插件。
提供禁漫天堂本子的查询、下载、搜索功能，下载后自动打包加密并发送到QQ群。

## ✨ 功能

| 命令 | 说明 |
|:---|:---|
| `/jm info <album_id>` | 查询本子详情（标题、作者、标签、章节列表等） |
| `/jm download <album_id>` | 下载本子 → 自动打包加密zip → 发送到QQ群 |
| `/jm search <keyword>` | 搜索本子 |
| `/jm help` | 查看帮助 |

### 下载流程
```
📥 下载本子 → 🗜️ 自动打包加密zip → 📤 发送到QQ群
                                       └─ ❌ 失败则提示服务器路径
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
| `auto_clean_days` | int | 7 | 文件保留天数（超过此天数自动删除） |
| `rate_limit_enabled` | bool | true | 是否开启1分钟使用次数限制 |
| `rate_limit_max_calls` | int | 5 | 每分钟最大调用次数 |

## 📖 使用示例

```
/jm info 350234
→ 查询本子 JM350234 的详情

/jm download 123
→ 下载本子 JM123 → 自动打包为 `123.zip`（密码=123）→ 发送到QQ群

/jm search 火影
→ 搜索标题/作者/标签包含"火影"的本子
```

## 🔗 相关链接

- [JMComic-Crawler-Python](https://github.com/hect0x7/JMComic-Crawler-Python)
- [jmcomic 文档](https://jmcomic.readthedocs.io/zh-cn/latest)
