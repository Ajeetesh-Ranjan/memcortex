// The AI Architecture Lab — Unified Memory Stack Native macOS Menubar App
// Build: swift build -c release
// Run: .build/release/MemoryMenubar
//
// Features:
// - Native macOS menubar integration
// - Real-time status updates
// - Click to open dashboard
// - Right-click menu with actions
// - Auto-refresh
// - No external dependencies (pure Swift/SwiftUI)

import SwiftUI
import AppKit
import Combine
import UserNotifications

// MARK: - Models

struct MemoryOverview: Codable {
    let supermemory: ServiceStatus
    let qdrant: ServiceStatus
    let redis: ServiceStatus
    let postgres: ServiceStatus
    let headroom: ServiceStatus
    let tokens: TokenStatus
    
    struct ServiceStatus: Codable {
        let up: Bool
        let memories: Int?
        let documents: Int?
    }
    
    struct TokenStatus: Codable {
        let saved: Int
        let ratio: Double
    }
}

struct HealthResponse: Codable {
    let status: String
}

struct AutopilotStatus: Codable {
    let enabled: Bool
    let recent: [AutopilotAction]
    
    struct AutopilotAction: Codable {
        let actor: String
        let category: String
        let action: String
        let target: String
        let result: String
        let ts: String
    }
}

// MARK: - API Client

class MemoryAPI: ObservableObject {
    let baseURL: String
    private let session = URLSession.shared
    private var refreshTimer: Timer?
    
    @Published var overview: MemoryOverview?
    @Published var autopilot: AutopilotStatus?
    @Published var isConnected = false
    @Published var lastError: String?
    
    var memoryCount: Int { overview?.supermemory.memories ?? 0 }
    var tokensSaved: Int { overview?.tokens.saved ?? 0 }
    var servicesUp: Int {
        [overview?.supermemory.up, overview?.qdrant.up, overview?.redis.up, overview?.postgres.up, overview?.headroom.up]
            .compactMap { $0 }
            .filter { $0 }
            .count
    }
    var servicesTotal: Int {
        [overview?.supermemory.up, overview?.qdrant.up, overview?.redis.up, overview?.postgres.up, overview?.headroom.up]
            .compactMap { $0 }
            .count
    }
    var overallStatus: Status {
        guard let overview = overview else { return .unknown }
        let up = servicesUp
        let total = servicesTotal
        if up == 0 { return .unhealthy }
        if up == total { return .healthy }
        return .degraded
    }
    
    enum Status { case healthy, degraded, unhealthy, unknown }
    
    init(baseURL: String = "http://localhost:8080") {
        self.baseURL = baseURL
        startRefresh()
        refresh()
    }
    
    deinit {
        refreshTimer?.invalidate()
    }
    
    func startRefresh() {
        refreshTimer = Timer.scheduledTimer(withTimeInterval: 30, repeats: true) { [weak self] _ in
            self?.refresh()
        }
        // Also listen for wake from sleep
        NSWorkspace.shared.notificationCenter.addObserver(
            forName: NSWorkspace.didWakeNotification,
            object: nil,
            queue: .main
        ) { [weak self] _ in
            self?.refresh()
        }
    }
    
    func refresh() {
        fetchOverview()
        fetchAutopilot()
    }
    
    private func fetchOverview() {
        guard let url = URL(string: "\(baseURL)/api/overview") else { return }
        
        session.dataTask(with: url) { [weak self] data, response, error in
            DispatchQueue.main.async {
                if let error = error {
                    self?.isConnected = false
                    self?.lastError = error.localizedDescription
                    return
                }
                
                guard let data = data,
                      let httpResponse = response as? HTTPURLResponse,
                      httpResponse.statusCode == 200,
                      let overview = try? JSONDecoder().decode(MemoryOverview.self, from: data) else {
                    self?.isConnected = false
                    return
                }
                
                self?.overview = overview
                self?.isConnected = true
                self?.lastError = nil
            }
        }.resume()
    }
    
    private func fetchAutopilot() {
        guard let url = URL(string: "\(baseURL)/api/autopilot/status") else { return }
        
        session.dataTask(with: url) { [weak self] data, response, error in
            DispatchQueue.main.async {
                if let data = data,
                   let response = response as? HTTPURLResponse,
                   response.statusCode == 200,
                   let autopilot = try? JSONDecoder().decode(AutopilotStatus.self, from: data) {
                    self?.autopilot = autopilot
                }
            }
        }.resume()
    }
}

// MARK: - Menubar Manager

class MenubarManager {
    let api = MemoryAPI()
    var statusItem: NSStatusItem?
    var popover: NSPopover?
    var eventMonitor: EventMonitor?
    
    init() {
        setupMenubar()
        setupPopover()
        setupEventMonitor()
        
        // Observe API changes
        api.objectWillChange.sink { [weak self] in
            self?.updateMenubar()
        }.store(in: &cancellables)
        
        // Initial update
        updateMenubar()
    }
    
    private var cancellables = Set<AnyCancellable>()
    
    private func setupMenubar() {
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        
        if let button = statusItem?.button {
            button.action = #selector(togglePopover(_:))
            button.sendAction(on: [.leftMouseUp, .rightMouseUp])
            button.target = self
        }
    }
    
    private func setupPopover() {
        popover = NSPopover()
        popover?.behavior = .transient
        popover?.contentViewController = NSHostingController(rootView: PopoverView(api: api))
    }
    
    private func setupEventMonitor() {
        eventMonitor = EventMonitor(mask: [.leftMouseDown, .rightMouseDown]) { [weak self] event in
            if let popover = self?.popover, popover.isShown {
                self?.closePopover()
            }
        }
    }
    
    @objc func togglePopover(_ sender: Any?) {
        guard let button = statusItem?.button else { return }
        
        if popover?.isShown == true {
            closePopover()
        } else {
            showPopover(button)
        }
    }
    
    func showPopover(_ button: NSStatusBarButton) {
        popover?.show(relativeTo: button.bounds, of: button, preferredEdge: .minY)
        eventMonitor?.start()
    }
    
    func closePopover() {
        popover?.performClose(nil)
        eventMonitor?.stop()
    }
    
    func updateMenubar() {
        guard let button = statusItem?.button else { return }
        
        let status = api.overallStatus
        let count = api.memoryCount
        
        // Create status icon
        let icon = createStatusIcon(status: status, count: count)
        button.image = icon
        button.image?.isTemplate = false
        
        // Tooltip
        let tooltip = """
        Unified Memory Stack
        Memories: \(api.memoryCount.formatted())
        Tokens saved: \(api.tokensSaved.formatted())
        Services: \(api.servicesUp)/\(api.servicesTotal) healthy
        Status: \(statusString(status))
        Click for details · Right-click for menu
        """
        button.toolTip = tooltip
    }
    
    private func statusString(_ status: MemoryAPI.Status) -> String {
        switch status {
        case .healthy: return "Healthy"
        case .degraded: return "Degraded"
        case .unhealthy: return "Unhealthy"
        case .unknown: return "Unknown"
        }
    }
    
    private func createStatusIcon(status: MemoryAPI.Status, count: Int) -> NSImage {
        let size = NSSize(width: 18, height: 18)
        let image = NSImage(size: size)
        image.lockFocus()
        
        let color: NSColor
        switch status {
        case .healthy: color = NSColor(calibratedRed: 0, green: 0.9, blue: 0.66, alpha: 1)
        case .degraded: color = NSColor(calibratedRed: 1, green: 0.71, blue: 0.33, alpha: 1)
        case .unhealthy: color = NSColor(calibratedRed: 1, green: 0.42, blue: 0.42, alpha: 1)
        case .unknown: color = NSColor(calibratedRed: 0.56, green: 0.64, blue: 0.73, alpha: 1)
        }
        
        // Draw circle
        let rect = NSRect(x: 1, y: 1, width: 16, height: 16)
        let path = NSBezierPath(ovalIn: rect)
        color.setFill()
        path.fill()
        
        // Border
        NSColor(white: 0.1, alpha: 1).setStroke()
        path.lineWidth = 1
        path.stroke()
        
        // Brain symbol
        let brainPath = NSBezierPath()
        brainPath.move(to: NSPoint(x: 9, y: 6))
        brainPath.curve(to: NSPoint(x: 9, y: 14), controlPoint1: NSPoint(x: 6, y: 6), controlPoint2: NSPoint(x: 6, y: 14))
        brainPath.move(to: NSPoint(x: 6, y: 10))
        brainPath.line(to: NSPoint(x: 12, y: 10))
        brainPath.move(to: NSPoint(x: 9, y: 7))
        brainPath.line(to: NSPoint(x: 9, y: 13))
        NSColor(white: 0.1, alpha: 1).setStroke()
        brainPath.lineWidth = 1.5
        brainPath.stroke()
        
        // Badge
        if count > 0 {
            let badgeText = count > 99 ? "99+" : "\(count)"
            let attrs: [NSAttributedString.Key: Any] = [
                .font: NSFont.boldSystemFont(ofSize: 8),
                .foregroundColor: NSColor(white: 0.05, alpha: 1)
            ]
            let textSize = badgeText.size(withAttributes: attrs)
            let badgeRect = NSRect(
                x: size.width - textSize.width - 6,
                y: size.height - textSize.height - 4,
                width: textSize.width + 4,
                height: textSize.height + 2
            )
            let badgePath = NSBezierPath(roundedRect: badgeRect, xRadius: 6, yRadius: 6)
            let badgeColor: NSColor
            if count > 50 { badgeColor = NSColor(calibratedRed: 1, green: 0.42, blue: 0.42, alpha: 1) }
            else if count > 10 { badgeColor = NSColor(calibratedRed: 1, green: 0.71, blue: 0.33, alpha: 1) }
            else { badgeColor = NSColor(calibratedRed: 0, green: 0.9, blue: 0.66, alpha: 1) }
            badgeColor.setFill()
            badgePath.fill()
            badgeText.draw(at: NSPoint(x: badgeRect.minX + 2, y: badgeRect.minY), withAttributes: attrs)
        }
        
        image.unlockFocus()
        return image
    }
}

// MARK: - Popover View

struct PopoverView: View {
    @ObservedObject var api: MemoryAPI
    @State private var showAutopilot = false
    
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            // Header
            HStack {
                Image(systemName: "brain.head.profile")
                    .font(.title2)
                    .foregroundColor(statusColor)
                VStack(alignment: .leading) {
                    Text("The AI Architecture Lab")
                        .font(.headline)
                    Text(statusText)
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
                Spacer()
                Button(action: { api.refresh() }) {
                    Image(systemName: "arrow.clockwise")
                }
                .buttonStyle(.borderless)
            }
            
            Divider()
            
            // Metrics
            HStack(spacing: 16) {
                MetricCard(title: "Memories", value: api.memoryCount.formatted(), icon: "archivebox.fill")
                MetricCard(title: "Tokens Saved", value: api.tokensSaved.formatted(), icon: "arrow.down.circle.fill")
                MetricCard(title: "Services", value: "\(api.servicesUp)/\(api.servicesTotal)", icon: "server.rack")
            }
            
            Divider()
            
            // Services
            VStack(alignment: .leading, spacing: 4) {
                Text("Services")
                    .font(.caption)
                    .foregroundColor(.secondary)
                
                ServiceRow(name: "Supermemory", up: api.overview?.supermemory.up)
                ServiceRow(name: "Qdrant", up: api.overview?.qdrant.up)
                ServiceRow(name: "Redis", up: api.overview?.redis.up)
                ServiceRow(name: "PostgreSQL", up: api.overview?.postgres.up)
                ServiceRow(name: "Headroom", up: api.overview?.headroom.up)
            }
            
            Divider()
            
            // Autopilot
            if let autopilot = api.autopilot, autopilot.enabled {
                VStack(alignment: .leading, spacing: 4) {
                    HStack {
                        Text("Autopilot")
                            .font(.caption)
                            .foregroundColor(.secondary)
                        Spacer()
                        Toggle("", isOn: $showAutopilot)
                            .labelsHidden()
                    }
                    
                    if showAutopilot {
                        ForEach(autopilot.recent.prefix(5), id: \.ts) { action in
                            HStack {
                                Circle()
                                    .fill(actionColor(action.result))
                                    .frame(width: 6, height: 6)
                                Text("\(action.category)/\(action.action)")
                                    .font(.caption)
                                Spacer()
                                Text(formatTime(action.ts))
                                    .font(.caption2)
                                    .foregroundColor(.secondary)
                            }
                        }
                    }
                }
            }
            
            Divider()
            
            // Actions
            HStack(spacing: 8) {
                Button("Open Dashboard") {
                    NSWorkspace.shared.open(URL(string: "http://localhost:8080")!)
                }
                .buttonStyle(.borderedProminent)
                
                Button("View Logs") {
                    openLogs()
                }
                .buttonStyle(.bordered)
                
                Button("Restart") {
                    restartStack()
                }
                .buttonStyle(.bordered)
            }
            
            if let error = api.lastError {
                Text("Error: \(error)")
                    .font(.caption)
                    .foregroundColor(.red)
            }
        }
        .padding(12)
        .frame(width: 300)
    }
    
    private var statusColor: Color {
        switch api.overallStatus {
        case .healthy: return .green
        case .degraded: return .orange
        case .unhealthy: return .red
        case .unknown: return .gray
        }
    }
    
    private var statusText: String {
        "\(statusString(api.overallStatus)) · \(api.servicesUp)/\(api.servicesTotal) services"
    }
    
    private func statusString(_ status: MemoryAPI.Status) -> String {
        switch status {
        case .healthy: return "Healthy"
        case .degraded: return "Degraded"
        case .unhealthy: return "Unhealthy"
        case .unknown: return "Unknown"
        }
    }
    
    private func actionColor(_ result: String) -> Color {
        switch result {
        case "ok": return .green
        case "fixed": return .blue
        case "skipped": return .orange
        default: return .red
        }
    }
    
    private func formatTime(_ ts: String) -> String {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let date = formatter.date(from: ts) {
            let formatter = DateFormatter()
            formatter.timeStyle = .short
            return formatter.string(from: date)
        }
        return ts
    }
    
    private func openLogs() {
        let task = Process()
        task.launchPath = "/usr/bin/open"
        task.arguments = ["-a", "Terminal", "--args", "docker", "compose", "logs", "-f", "--tail", "100"]
        task.launch()
    }
    
    private func restartStack() {
        let task = Process()
        task.launchPath = "/bin/bash"
        task.arguments = ["-c", "cd \(FileManager.default.currentDirectoryPath) && docker compose restart"]
        task.launch()
    }
}

struct MetricCard: View {
    let title: String
    let value: String
    let icon: String
    
    var body: some View {
        VStack(spacing: 2) {
            Image(systemName: icon)
                .font(.title3)
                .foregroundColor(.accentColor)
            Text(value)
                .font(.system(.title3, design: .rounded).bold())
            Text(title)
                .font(.caption2)
                .foregroundColor(.secondary)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 6)
        .background(Color(NSColor.controlBackgroundColor))
        .cornerRadius(8)
    }
}

struct ServiceRow: View {
    let name: String
    let up: Bool?
    
    var body: some View {
        HStack {
            Circle()
                .fill(up == true ? Color.green : (up == false ? Color.red : Color.gray))
                .frame(width: 6, height: 6)
            Text(name)
                .font(.caption)
            Spacer()
            Text(up == true ? "UP" : (up == false ? "DOWN" : "—"))
                .font(.caption.monospaced())
                .foregroundColor(up == true ? .green : (up == false ? .red : .secondary))
        }
    }
}

// MARK: - Event Monitor

class EventMonitor {
    private var monitor: Any?
    private let mask: NSEvent.EventTypeMask
    private let handler: (NSEvent) -> Void
    
    init(mask: NSEvent.EventTypeMask, handler: @escaping (NSEvent) -> Void) {
        self.mask = mask
        self.handler = handler
    }
    
    func start() {
        monitor = NSEvent.addGlobalMonitorForEvents(matching: mask) { [weak self] event in
            self?.handler(event)
        }
    }
    
    func stop() {
        if let monitor = monitor {
            NSEvent.removeMonitor(monitor)
            self.monitor = nil
        }
    }
    
    deinit {
        stop()
    }
}

// MARK: - App Delegate

class AppDelegate: NSObject, NSApplicationDelegate {
    var menubarManager: MenubarManager?
    
    func applicationDidFinishLaunching(_ notification: Notification) {
        // Hide dock icon (menubar-only app)
        NSApp.setActivationPolicy(.accessory)
        
        // Request notification permission
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound]) { _, _ in }
        
        menubarManager = MenubarManager()
    }
    
    func applicationWillTerminate(_ notification: Notification) {
        menubarManager?.eventMonitor?.stop()
    }
}

// MARK: - Main

@main
struct MemoryMenubarApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) var appDelegate
    
    var body: some Scene {
        Settings {
            EmptyView()
        }
    }
}