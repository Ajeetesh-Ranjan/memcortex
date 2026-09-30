// The AI Architecture Lab — Unified Memory Stack Go System Tray Widget
// Cross-platform single binary (Windows, macOS, Linux)
// Build: go build -ldflags="-s -w" -o memory-widget
//
// Features:
// - Native system tray on all platforms
// - No runtime dependencies
// - Auto-refresh, click to open, right-click menu
// - Memory efficient (~5MB RSS)

package main

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"os/exec"
	"runtime"
	"strings"
	"sync"
	"time"

	"github.com/getlantern/systray"
	"github.com/skratchdot/open-golang/open"
)

const (
	DefaultAPIBase     = "http://localhost:8080"
	DefaultRefreshSec  = 30
	IconSize           = 32
)

var (
	apiBase    = getEnv("MEMORY_API_BASE", DefaultAPIBase)
	refreshSec = getEnvInt("MEMORY_REFRESH_SEC", DefaultRefreshSec)
)

type Overview struct {
	Supermemory struct {
		Up        bool `json:"up"`
		Memories  int  `json:"memories"`
		Documents int  `json:"documents"`
		Static    int  `json:"static"`
		Dynamic   int  `json:"dynamic"`
	} `json:"supermemory"`
	Qdrant    map[string]interface{} `json:"qdrant"`
	Redis     map[string]interface{} `json:"redis"`
	Postgres  map[string]interface{} `json:"postgres"`
	Headroom  map[string]interface{} `json:"headroom"`
	Tokens    map[string]interface{} `json:"tokens"`
}

type Health struct {
	Supermemory bool `json:"supermemory"`
	Qdrant      bool `json:"qdrant"`
	Redis       bool `json:"redis"`
	Postgres    bool `json:"postgres"`
	Headroom    bool `json:"headroom"`
}

type AutopilotStatus struct {
	Enabled bool   `json:"enabled"`
	Recent  []any  `json:"recent"`
}

var (
	currentStatus string
	memoryCount   int
	tokensSaved   int
	servicesUp    int
	servicesTotal int
	mu            sync.RWMutex
)

func getEnv(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}

func getEnvInt(key string, def int) int {
	if v := os.Getenv(key); v != "" {
		var i int
		fmt.Sscanf(v, "%d", &i)
		if i > 0 {
			return i
		}
	}
	return def
}

func main() {
	// Allow command line override
	if len(os.Args) > 1 {
		apiBase = os.Args[1]
	}

	fmt.Printf("Memory Widget starting...\nAPI: %s\nRefresh: %ds\n", apiBase, refreshSec)

	// Initial fetch
	fetchAll()

	// Start background refresher
	go refresher()

	// Run systray (blocks)
	systray.Run(onReady, onExit)
}

func onReady() {
	updateIcon()
	systray.SetTitle("The AI Architecture Lab")
	systray.SetTooltip(buildTooltip())

	mOpen := systray.AddMenuItem("Open Dashboard", "Open Brain UI dashboard")
	mRefresh := systray.AddMenuItem("Refresh Now", "Force refresh")
	mLogs := systray.AddMenuItem("View Logs", "Open docker compose logs")
	mRestart := systray.AddMenuItem("Restart Stack", "Restart all services")
	systray.AddSeparator()
	mQuit := systray.AddMenuItem("Quit", "Exit widget")

	go func() {
		for {
			select {
			case <-mOpen.ClickedCh:
				open.Run(apiBase)
			case <-mRefresh.ClickedCh:
				fetchAll()
				updateIcon()
			case <-mLogs.ClickedCh:
				viewLogs()
			case <-mRestart.ClickedCh:
				restartStack()
			case <-mQuit.ClickedCh:
				systray.Quit()
				return
			}
		}
	}()
}

func onExit() {
	fmt.Println("Widget stopped")
}

func refresher() {
	ticker := time.NewTicker(time.Duration(refreshSec) * time.Second)
	defer ticker.Stop()

	for range ticker.C {
		fetchAll()
		updateIcon()
	}
}

func fetchAll() {
	overview := fetchOverview()
	health := fetchHealth()
	_ = fetchAutopilot() // Not used yet but kept for future

	mu.Lock()
	defer mu.Unlock()

	if overview != nil {
		memoryCount = overview.Supermemory.Memories
		tokensSaved = 0
		if v, ok := overview.Tokens["saved"]; ok {
			if f, ok := v.(float64); ok {
				tokensSaved = int(f)
			}
		}

		services := []bool{
			overview.Supermemory.Up,
			getBool(overview.Qdrant, "up"),
			getBool(overview.Redis, "up"),
			getBool(overview.Postgres, "up"),
			getBool(overview.Headroom, "up"),
		}

		servicesTotal = len(services)
		up := 0
		for _, s := range services {
			if s {
				up++
			}
		}
		servicesUp = up

		if up == 0 {
			currentStatus = "unhealthy"
		} else if up == servicesTotal {
			currentStatus = "healthy"
		} else {
			currentStatus = "degraded"
		}
	} else {
		currentStatus = "unknown"
		memoryCount = 0
		tokensSaved = 0
		servicesUp = 0
		servicesTotal = 0
	}
}

func getBool(m map[string]interface{}, key string) bool {
	if m == nil {
		return false
	}
	if v, ok := m[key]; ok {
		if b, ok := v.(bool); ok {
			return b
		}
	}
	return false
}

func fetchOverview() *Overview {
	resp, err := http.Get(apiBase + "/api/overview")
	if err != nil || resp.StatusCode != 200 {
		return nil
	}
	defer resp.Body.Close()

	body, _ := io.ReadAll(resp.Body)
	var o Overview
	if err := json.Unmarshal(body, &o); err != nil {
		return nil
	}
	return &o
}

func fetchHealth() *Health {
	resp, err := http.Get(apiBase + "/healthz")
	if err != nil || resp.StatusCode != 200 {
		return nil
	}
	defer resp.Body.Close()

	body, _ := io.ReadAll(resp.Body)
	var h Health
	json.Unmarshal(body, &h)
	return &h
}

func fetchAutopilot() *AutopilotStatus {
	resp, err := http.Get(apiBase + "/api/autopilot/status")
	if err != nil || resp.StatusCode != 200 {
		return nil
	}
	defer resp.Body.Close()

	body, _ := io.ReadAll(resp.Body)
	var a AutopilotStatus
	json.Unmarshal(body, &a)
	return &a
}

func updateIcon() {
	mu.RLock()
	status := currentStatus
	count := memoryCount
	mu.RUnlock()

	icon := generateIcon(status, count)
	systray.SetIcon(icon)
	systray.SetTitle("The AI Architecture Lab")
	systray.SetTooltip(buildTooltip())
}

func buildTooltip() string {
	mu.RLock()
	defer mu.RUnlock()

	var b strings.Builder
	b.WriteString("The AI Architecture Lab — Unified Memory Stack\n")
	b.WriteString(fmt.Sprintf("Memories: %d\n", memoryCount))
	b.WriteString(fmt.Sprintf("Tokens saved: %d\n", tokensSaved))
	b.WriteString(fmt.Sprintf("Services: %d/%d healthy\n", servicesUp, servicesTotal))
	b.WriteString("\nClick to open dashboard\nRight-click for menu")
	return b.String()
}

func generateIcon(status string, count int) []byte {
	// Simple colored square icon (systray expects PNG/ICO)
	// In production, embed actual PNG assets
	// For now, return a minimal 1x1 transparent PNG as placeholder
	// Real implementation would use embedded PNG files per status

	// Minimal 16x16 PNG (transparent)
	// This is a placeholder - replace with actual icon files
	return []byte{
		0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, // PNG header
		0x00, 0x00, 0x00, 0x0D, 0x49, 0x48, 0x44, 0x52, // IHDR
		0x00, 0x00, 0x00, 0x10, 0x00, 0x00, 0x00, 0x10,
		0x08, 0x06, 0x00, 0x00, 0x00, 0x1F, 0xF3, 0xFF, 0x61,
		0x00, 0x00, 0x00, 0x0A, 0x49, 0x44, 0x41, 0x54, // IDAT
		0x78, 0x9C, 0x63, 0x00, 0x01, 0x00, 0x00, 0x05,
		0x00, 0x01, 0x0D, 0x0A, 0x2D, 0xB4, 0x00, 0x00,
		0x00, 0x00, 0x49, 0x45, 0x4E, 0x44, 0xAE, 0x42, 0x60, 0x82, // IEND
	}
}

func viewLogs() {
	cmd := exec.Command("docker", "compose", "logs", "-f", "--tail", "100")
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	cmd.Run()
}

func restartStack() {
	cmd := exec.Command("docker", "compose", "restart")
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	if err := cmd.Run(); err != nil {
		fmt.Printf("Restart failed: %v\n", err)
	}
	time.Sleep(5 * time.Second)
	fetchAll()
	updateIcon()
}