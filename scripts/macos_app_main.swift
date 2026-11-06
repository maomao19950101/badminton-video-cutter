import Cocoa
import WebKit

@main
class AppDelegate: NSObject, NSApplicationDelegate, WKUIDelegate, WKNavigationDelegate, NSWindowDelegate {
    var window: NSWindow!
    var webView: WKWebView!
    var serverProcess: Process?
    var targetURLString: String = "http://127.0.0.1:18765"

    static func main() {
        let app = NSApplication.shared
        let delegate = AppDelegate()
        app.delegate = delegate
        app.setActivationPolicy(.regular)
        app.run()
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        parseCommandLineArgs()
        setupAppIcon()
        setupMainMenu()
        setupMainWindow()
        ensureBackendAndLoad()
    }

    private func parseCommandLineArgs() {
        for arg in CommandLine.arguments {
            if arg.hasPrefix("--url=") {
                let val = String(arg.dropFirst("--url=".count))
                if !val.isEmpty {
                    targetURLString = val
                }
            }
        }
    }

    private func setupAppIcon() {
        if let icnsPath = Bundle.main.path(forResource: "AppIcon", ofType: "icns"),
           let img = NSImage(contentsOfFile: icnsPath) {
            NSApp.applicationIconImage = img
        }
    }

    private func setupMainMenu() {
        let mainMenu = NSMenu()

        // App Menu
        let appMenuItem = NSMenuItem()
        mainMenu.addItem(appMenuItem)
        let appMenu = NSMenu()
        appMenuItem.submenu = appMenu
        appMenu.addItem(withTitle: "关于 羽毛球AI剪辑大师", action: #selector(NSApplication.orderFrontStandardAboutPanel(_:)), keyEquivalent: "")
        appMenu.addItem(NSMenuItem.separator())
        appMenu.addItem(withTitle: "隐藏 羽毛球AI剪辑大师", action: #selector(NSApplication.hide(_:)), keyEquivalent: "h")
        appMenu.addItem(NSMenuItem.separator())
        appMenu.addItem(withTitle: "退出 羽毛球AI剪辑大师", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")

        // Edit Menu (for copy/paste/select all in text inputs)
        let editMenuItem = NSMenuItem()
        mainMenu.addItem(editMenuItem)
        let editMenu = NSMenu(title: "编辑")
        editMenuItem.submenu = editMenu
        editMenu.addItem(withTitle: "撤销", action: Selector(("undo:")), keyEquivalent: "z")
        editMenu.addItem(withTitle: "重做", action: Selector(("redo:")), keyEquivalent: "Z")
        editMenu.addItem(NSMenuItem.separator())
        editMenu.addItem(withTitle: "剪切", action: #selector(NSText.cut(_:)), keyEquivalent: "x")
        editMenu.addItem(withTitle: "拷贝", action: #selector(NSText.copy(_:)), keyEquivalent: "c")
        editMenu.addItem(withTitle: "粘贴", action: #selector(NSText.paste(_:)), keyEquivalent: "v")
        editMenu.addItem(withTitle: "全选", action: #selector(NSText.selectAll(_:)), keyEquivalent: "a")

        NSApp.mainMenu = mainMenu
    }

    private func setupMainWindow() {
        let screenRect = NSScreen.main?.visibleFrame ?? NSRect(x: 0, y: 0, width: 1600, height: 1000)
        let winW: CGFloat = min(1480, screenRect.width * 0.94)
        let winH: CGFloat = min(920, screenRect.height * 0.92)
        let originX = screenRect.origin.x + (screenRect.width - winW) / 2.0
        let originY = screenRect.origin.y + (screenRect.height - winH) / 2.0

        let contentRect = NSRect(x: originX, y: originY, width: winW, height: winH)
        let styleMask: NSWindow.StyleMask = [.titled, .closable, .miniaturizable, .resizable]

        window = NSWindow(contentRect: contentRect, styleMask: styleMask, backing: .buffered, defer: false)
        window.title = "Codex Studio · 羽毛球 AI 视频剪辑大师 v1.8.0"
        window.minSize = NSSize(width: 1120, height: 720)
        window.backgroundColor = NSColor(calibratedRed: 0.05, green: 0.05, blue: 0.05, alpha: 1.0)
        window.delegate = self
        window.isReleasedWhenClosed = false

        let config = WKWebViewConfiguration()
        config.mediaTypesRequiringUserActionForPlayback = []

        webView = WKWebView(frame: window.contentView!.bounds, configuration: config)
        webView.autoresizingMask = [.width, .height]
        webView.uiDelegate = self
        webView.navigationDelegate = self
        webView.setValue(false, forKey: "drawsBackground")

        window.contentView?.addSubview(webView)
        bringWindowToFront()
    }

    func bringWindowToFront() {
        window.makeKeyAndOrderFront(nil)
        window.orderFrontRegardless()
        NSApp.activate(ignoringOtherApps: true)
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.25) {
            self.window.makeKeyAndOrderFront(nil)
            self.window.orderFrontRegardless()
            NSApp.activate(ignoringOtherApps: true)
        }
    }

    private func isServerAlive(completion: @escaping (Bool) -> Void) {
        guard let url = URL(string: "\(targetURLString)/api/state") else {
            completion(false)
            return
        }
        let cfg = URLSessionConfiguration.ephemeral
        cfg.connectionProxyDictionary = [:]
        cfg.timeoutIntervalForRequest = 0.7
        let session = URLSession(configuration: cfg)
        session.dataTask(with: url) { data, response, error in
            if let httpResp = response as? HTTPURLResponse, httpResp.statusCode == 200, data != nil {
                completion(true)
            } else {
                completion(false)
            }
        }.resume()
    }

    private func ensureBackendAndLoad() {
        isServerAlive { [weak self] alive in
            guard let self = self else { return }
            if alive {
                DispatchQueue.main.async {
                    self.loadStudioURL()
                }
            } else {
                self.startPythonBackend()
                self.pollUntilReady(retries: 25)
            }
        }
    }

    private func startPythonBackend() {
        let scriptPath = ProcessInfo.processInfo.environment["BADMINTON_STUDIO_SCRIPT"]
            ?? Bundle.main.url(forResource: "codex_server", withExtension: "py", subdirectory: "scripts")?.path
            ?? ""
        guard FileManager.default.fileExists(atPath: scriptPath) else { return }

        let proc = Process()
        proc.executableURL = URL(fileURLWithPath: "/usr/bin/env")
        proc.arguments = ["python3", scriptPath, "--no-open", "--port", "18765"]
        var env = ProcessInfo.processInfo.environment
        let extraPath = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
        env["PATH"] = extraPath + ":" + (env["PATH"] ?? "")
        proc.environment = env
        proc.standardOutput = FileHandle.nullDevice
        proc.standardError = FileHandle.nullDevice

        do {
            try proc.run()
            self.serverProcess = proc
        } catch {
            print("Failed to launch codex_server.py: \(error)")
        }
    }

    private func pollUntilReady(retries: Int) {
        if retries <= 0 {
            DispatchQueue.main.async {
                self.loadStudioURL()
            }
            return
        }
        DispatchQueue.global().asyncAfter(deadline: .now() + 0.15) { [weak self] in
            guard let self = self else { return }
            self.isServerAlive { alive in
                if alive {
                    DispatchQueue.main.async {
                        self.loadStudioURL()
                    }
                } else {
                    self.pollUntilReady(retries: retries - 1)
                }
            }
        }
    }

    private func loadStudioURL() {
        guard let url = URL(string: targetURLString) else { return }
        let req = URLRequest(url: url, cachePolicy: .reloadIgnoringLocalCacheData, timeoutInterval: 10)
        webView.load(req)
        bringWindowToFront()
    }

    // MARK: - WKUIDelegate (Native JS Alert & Confirm Dialogs)
    func webView(_ webView: WKWebView, runJavaScriptAlertPanelWithMessage message: String, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping () -> Void) {
        let alert = NSAlert()
        alert.messageText = "羽毛球 AI 剪辑大师"
        alert.informativeText = message
        alert.addButton(withTitle: "确定")
        alert.beginSheetModal(for: window) { _ in
            completionHandler()
        }
    }

    func webView(_ webView: WKWebView, runJavaScriptConfirmPanelWithMessage message: String, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (Bool) -> Void) {
        let alert = NSAlert()
        alert.messageText = "请确认操作"
        alert.informativeText = message
        alert.addButton(withTitle: "确定")
        alert.addButton(withTitle: "取消")
        alert.beginSheetModal(for: window) { response in
            completionHandler(response == .alertFirstButtonReturn)
        }
    }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        bringWindowToFront()
        return true
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        return true
    }

    func applicationWillTerminate(_ notification: Notification) {
        if let proc = serverProcess, proc.isRunning {
            proc.terminate()
        }
    }
}
