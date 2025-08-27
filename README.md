> English version: [README_EN.md](README_EN.md)

贊助我製作Android版本（需要25美元上架費）：  

[!["Buy Me A Coffee"](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://www.buymeacoffee.com/arttin)  

[![ko-fi](https://www.ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/U7U01KBWBU)  

# TaskTimer — 固定時長循環提醒器

用固定「時長」來提醒，而不是指定某年某月某日。你只要設定一個時長（像是 7 天、30 天），就能反覆用於訂閱/帳單/例行工作等周期性任務，時間到之後一鍵重設即可進入下一輪。

> 和一般日曆應用的核心差異：不是「預約未來某時刻的鬧鐘」，而是「以固定時長為單位的提醒」，實務上更適合訂閱制到期、試用到期、例行檢查、備份等情境。

## 特色

- 輕量、免費、開源、無廣告
- 任務可匯入/匯出
- 多個任務個別管理
- 說明欄位支援超連結預覽與點擊開啟瀏覽器
- 固定時長倒數與循環使用
	- 支援秒 / 分 / 時 / 天，快速輸入 1～99 並選擇單位。
	- 顯示目標時間與剩餘時間，到時彈出提醒。
	- 到時後任務仍保留，按一下「重設」即可開始下一輪（實務上可無限循環使用）。
- 通知體驗
	- 內建應用內輕量氣泡通知，可自訂顯示座標；點擊可直接開啟編輯。
	- 可選擇啟用 Windows 原生通知（winotify）。
- 設定與外觀
	- 深/淺色/跟隨系統三種主題；大字體、DPI 感知，顯示清晰。
	- 可選「開機自啟動」與「啟動時最小化至托盤」。

## 原始碼執行

開發環境：Windows 10/11, Python 3.13

1) 安裝依賴

```cmd
pip install -r requirements.txt
```

可選（托盤圖示）：

```cmd
pip install pystray pillow
```

2) 執行

```cmd
python TaskTimer.py
```

說明：
- 任務資料儲存在使用者目錄：`%USERPROFILE%\TaskTimer\tasks.json`。
- 設定檔 `TaskTimer.json`：
	- 直跑 .py：與 `TaskTimer.py` 同資料夾。
	- 打包 .exe：與 .exe 同資料夾。

## 使用說明

- 新增任務 → 輸入「數值 + 單位」→ 儲存。
- 開始/暫停：互不影響其他任務。
- 重設：直接將下一輪目標時間設為「現在 + 時長」。
- 通知：
	- 一定會有應用視窗提醒；
	- 若啟用「系統通知」，同時會顯示 Windows 通知。
- 開機自啟動：設定頁可一鍵啟用/停用（其原理是建立/刪除啟動資料夾捷徑）。
- 托盤：安裝可選依賴後，程式可縮到系統托盤常駐；未安裝則改為最小化。

## 特別感謝
GPT、Cluade、Gemini