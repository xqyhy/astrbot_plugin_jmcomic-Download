# 🦊 astrbot_plugin_jmcomic-Download

基于 [JMComic-Crawler-Python](https://github.com/hect0x7/JMComic-Crawler-Python) API 的 AstrBot 插件。
提供禁漫天堂本子的查询、下载、搜索功能。

## ✨ 功能

| 命令 | 说明 |
|:---|:---|
| `/jm info <album_id>` | 查询本子详情（标题、作者、标签、章节列表等） |
| `/jm download <album_id>` | 下载本子并自动打包为加密zip（密码=本子ID） |
| `/jm search <keyword>` | 搜索本子 |
| `/jm help` | 查看帮助 |

## 📦 安装

1. 确保 AstrBot 环境已安装 `jmcomic` 库：
   ```bash
   pip install jmcomic -U
   ```
2. 将本插件文件夹放入 `AstrBot/data/plugins/` 目录
3. 重启 AstrBot 或重载插件

## ⚙️ 配置

在 AstrBot 管理面板中可配置：

| 配置项 | 类型 | 默认值 | 说明 |
|:---|:---:|:---|:---|
| `download_dir` | string | 插件数据目录/downloads | 本子下载保存路径 |
| `auto_clean_enabled` | bool | false | 是否开启自动清理旧压缩包 |
| `auto_clean_days` | int | 7 | 文件保留天数（超过此天数自动删除） |

## 📖 使用示例

```
/jm info 350234
→ 查询本子 JM350234 的详情

/jm download 123
→ 下载本子 JM123 并自动打包为 `123.zip`，解压密码为 `123`

/jm search 火影
→ 搜索标题/作者/标签包含"火影"的本子
```

## 🔗 相关链接

- [JMComic-Crawler-Python](https://github.com/hect0x7/JMComic-Crawler-Python)
- [jmcomic 文档](https://jmcomic.readthedocs.io/zh-cn/latest)
