param(
  [string]$BaseUrl = 'http://192.168.1.94:8080'
)

$ErrorActionPreference = 'Stop'

function Get-TodayStats {
  return Invoke-RestMethod "$BaseUrl/api/log/today" -TimeoutSec 10
}

function Get-DailyStats {
  return Invoke-RestMethod "$BaseUrl/api/log/daily?days=7" -TimeoutSec 10
}

$beforeToday = Get-TodayStats
$beforeDaily = Get-DailyStats
$beforeOperations = Invoke-RestMethod "$BaseUrl/api/operations?limit=10" -TimeoutSec 10

$tag = 'frontend-log-alignment-' + [DateTimeOffset]::Now.ToUnixTimeMilliseconds()
$payload = @{
  message = "Reply with this test id: $tag"
  messages = @(
    @{ role = 'user'; content = "Reply with this test id: $tag" }
  )
} | ConvertTo-Json -Depth 5

$chatResponse = Invoke-RestMethod "$BaseUrl/api/chat/send" -Method Post `
  -ContentType 'application/json' -Body $payload -TimeoutSec 50

Start-Sleep -Seconds 3

$afterToday = Get-TodayStats
$afterDaily = Get-DailyStats
$context = Invoke-RestMethod "$BaseUrl/api/ai/context?limit=10" -TimeoutSec 10

$beforeChat = [int]$beforeToday.today.total_chat
$afterChat = [int]$afterToday.today.total_chat
$dailyChat = [int]$afterDaily.daily[-1].total_chat
$requestDelta = [int]$afterToday.today.total_requests - [int]$beforeToday.today.total_requests
$chatDelta = $afterChat - $beforeChat
$contextText = [string]$context.context

$checks = @(
  [PSCustomObject]@{ Check = 'today request count increased'; Passed = $requestDelta -gt 0; Detail = "delta=$requestDelta" }
  [PSCustomObject]@{ Check = 'today chat count increased'; Passed = $chatDelta -gt 0; Detail = "delta=$chatDelta" }
  [PSCustomObject]@{ Check = 'daily and today chat counts match'; Passed = $dailyChat -eq $afterChat; Detail = "daily=$dailyChat today=$afterChat" }
  [PSCustomObject]@{ Check = 'AI context contains test id'; Passed = $contextText.Contains($tag); Detail = $tag }
  [PSCustomObject]@{ Check = 'operations envelope has total'; Passed = $null -ne $beforeOperations.total; Detail = "total=$($beforeOperations.total)" }
  [PSCustomObject]@{ Check = 'chat endpoint returned reply'; Passed = -not [string]::IsNullOrWhiteSpace([string]$chatResponse.reply); Detail = [string]$chatResponse.reply }
)

$checks | Format-Table -AutoSize

$failed = @($checks | Where-Object { -not $_.Passed })
if ($failed.Count -gt 0) {
  Write-Error "$($failed.Count) log alignment check(s) failed."
  exit 1
}

Write-Host "PASS: all log alignment checks passed. chat delta=$chatDelta"
