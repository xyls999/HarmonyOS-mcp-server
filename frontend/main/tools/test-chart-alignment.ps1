param(
  [string]$BaseUrl = 'http://192.168.1.94:8080'
)

$ErrorActionPreference = 'Stop'

$allTypes = @(
  'daily_bar', 'daily_line', 'chat_line', 'ops_bar', 'security_pie', 'online_area',
  'today_gauge', 'overview', 'temp_line', 'humid_line', 'chat_source_pie', 'ops_heatmap',
  'security_trend', 'device_pie', 'device_status_bar', 'area_radar', 'energy_bar'
)
$supportedRenderers = @('bar', 'line', 'pie', 'gauge', 'radar')
$contractRows = @()
foreach ($type in $allTypes) {
  $response = Invoke-RestMethod "$BaseUrl/api/log/chart?type=$type&days=7" -TimeoutSec 15
  $charts = @($response.charts)
  $unsupported = @($charts | Where-Object { $supportedRenderers -notcontains $_.type })
  $contractRows += [PSCustomObject]@{
    Type = $type
    Returned = $response.chart_type
    Charts = $charts.Count
    Renderable = $charts.Count -gt 0 -and $unsupported.Count -eq 0
  }
}

$daily = Invoke-RestMethod "$BaseUrl/api/log/chart?type=daily_bar&days=7" -TimeoutSec 15
$today = Invoke-RestMethod "$BaseUrl/api/log/chart?type=today_gauge&days=7" -TimeoutSec 15

$dailyChart = $daily.charts | Where-Object { $_.id -eq 'daily_bar' } | Select-Object -First 1
$todayChart = $today.charts | Where-Object { $_.id -eq 'today_gauge' } | Select-Object -First 1
$seriesNames = @($dailyChart.series | ForEach-Object { $_.name })

$chartJson = $daily | ConvertTo-Json -Depth 20 -Compress
$message = "Analyze this ECharts data and summarize trends: $chartJson"
$payload = @{
  message = $message
  messages = @(@{ role = 'user'; content = $message })
} | ConvertTo-Json -Depth 8
$chat = Invoke-RestMethod "$BaseUrl/api/chat/send" -Method Post -ContentType 'application/json' `
  -Body $payload -TimeoutSec 55

$modelConfigured = -not ([string]$chat.reply).Contains('未配置AI') -and `
  -not ([string]$chat.reply).Contains('AI暂时不可用')

$checks = @(
  [PSCustomObject]@{ Check = 'daily chart type'; Passed = $daily.chart_type -eq 'daily_bar'; Detail = $daily.chart_type }
  [PSCustomObject]@{ Check = 'daily category axis'; Passed = @($dailyChart.xAxis.data).Count -gt 0; Detail = "points=$(@($dailyChart.xAxis.data).Count)" }
  [PSCustomObject]@{ Check = 'request series'; Passed = $seriesNames -contains '请求数'; Detail = ($seriesNames -join ',') }
  [PSCustomObject]@{ Check = 'chat series'; Passed = $seriesNames -contains '对话数'; Detail = ($seriesNames -join ',') }
  [PSCustomObject]@{ Check = 'operation series'; Passed = $seriesNames -contains '设备操作'; Detail = ($seriesNames -join ',') }
  [PSCustomObject]@{ Check = 'today gauge type'; Passed = $today.chart_type -eq 'today_gauge'; Detail = $today.chart_type }
  [PSCustomObject]@{ Check = 'today gauge data'; Passed = $null -ne $todayChart.data.total_requests; Detail = "requests=$($todayChart.data.total_requests)" }
)

$checks | Format-Table -AutoSize
$contractRows | Format-Table -AutoSize
Write-Host "AI_MODEL_CONFIGURED=$modelConfigured"
Write-Host "AI_REPLY=$($chat.reply)"

$failed = @($checks | Where-Object { -not $_.Passed })
$failedContracts = @($contractRows | Where-Object { -not $_.Renderable })
if ($failed.Count -gt 0 -or $failedContracts.Count -gt 0) {
  Write-Error "$($failed.Count) chart check(s) and $($failedContracts.Count) renderer contract(s) failed."
  exit 1
}

Write-Host 'PASS: all 17 ECharts contracts are supported by the frontend renderers.'
