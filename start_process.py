import json
import os
import subprocess
import psutil

# ====================== 配置区，只改这里 ======================
NEW_INDEX_ID = 2  # 要切换的节点IndexId数字
V2RAYN_EXE_PATH = r"C:\Users\%USERNAME%\Desktop\v2rayN-windows-64\v2rayN.exe"
CONFIG_FILE = r"C:\Users\%USERNAME%\Desktop\v2rayN-windows-64\guiConfigs\guiNConfig.json"
# ==========================================================

def kill_v2rayn():
    """优雅终止所有v2rayN进程"""
    for proc in psutil.process_iter(["name"]):
        if proc.info["name"] and proc.info["name"].lower() == "v2rayn.exe":
            try:
                proc.terminate()
                proc.wait(timeout=3)
                print(f"已关闭进程 PID:{proc.pid}")
            except Exception as e:
                proc.kill()
                print(f"强制杀死进程 PID:{proc.pid} 异常:{e}")

def modify_index_id(target_id: int):
    """修改guiNConfig.json的IndexId"""
    if not os.path.exists(CONFIG_FILE):
        raise FileNotFoundError("配置文件不存在，请检查路径")

    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    # v2rayN用数组存储，只修改第一个
    cfg["IndexId"][0] = target_id

    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

    print(f"已修改 IndexId 为: {target_id}")

def start_v2rayn():
    """后台启动v2rayN"""
    if not os.path.exists(V2RAYN_EXE_PATH):
        raise FileNotFoundError("v2rayN.exe 路径错误")

    subprocess.Popen([V2RAYN_EXE_PATH], creationflags=subprocess.CREATE_NO_WINDOW)
    print("已重新启动 v2rayN")

if __name__ == "__main__":
    try:
        kill_v2rayn()
        modify_index_id(NEW_INDEX_ID)
        start_v2rayn()
        print("✅ 全部执行完成")
    except Exception as err:
        print(f"❌ 执行失败: {err}")