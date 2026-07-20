import json
import urllib.request

source = "第一句：系统检测到客厅温度变化。第二句：已读取设备状态并给出调整建议。第三句：来自 weather 的 AI 新闻 https://www.chinanews.com.cn/rss/scroll-news.xml。" * 3
body = json.dumps({"text": source, "category": "direct_probe_long"}, ensure_ascii=False).encode("utf-8")
request = urllib.request.Request("http://127.0.0.1:8080/api/tts/speak", data=body,
                                 headers={"Content-Type": "application/json"}, method="POST")
with urllib.request.urlopen(request, timeout=10) as response:
    result = json.loads(response.read().decode("utf-8"))
    print(json.dumps({"speechText": result["speechText"], "length": len(result["speechText"]),
                      "hasPlaceholder": "相关信息" in result["speechText"]}, ensure_ascii=False).encode("utf-8"))
