$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $PSScriptRoot
$devecoRoot = 'D:\devEco\DevEco Studio'
$sdkRoot = 'D:\ohos12\12'
$unsignedHap = Join-Path $projectRoot 'entry\build\default\outputs\default\entry-default-unsigned.hap'
$signedHap = Join-Path $projectRoot 'entry\build\default\outputs\default\entry-default-signed.hap'
$signingDir = Join-Path $projectRoot '.openharmony-signing'

$env:NODE_HOME = Join-Path $devecoRoot 'tools\node'
$env:JAVA_HOME = Join-Path $devecoRoot 'jbr'
$env:PATH = "$env:NODE_HOME;$env:JAVA_HOME\bin;$env:PATH"

& (Join-Path $devecoRoot 'tools\hvigor\bin\hvigorw.bat') `
  --mode module `
  -p product=default `
  -p module=entry@default `
  -p buildMode=debug `
  assembleHap `
  --no-daemon

if ($LASTEXITCODE -ne 0) {
  throw 'OpenHarmony HAP build failed.'
}

& (Join-Path $env:JAVA_HOME 'bin\java.exe') `
  -jar (Join-Path $sdkRoot 'toolchains\lib\hap-sign-tool.jar') `
  sign-app `
  -mode localSign `
  -keyAlias 'openharmony application release' `
  -keyPwd 123456 `
  -appCertFile (Join-Path $signingDir 'app-release-chain.cer') `
  -profileFile (Join-Path $signingDir 'profile-release.p7b') `
  -profileSigned 1 `
  -inFile $unsignedHap `
  -signAlg SHA256withECDSA `
  -keystoreFile (Join-Path $sdkRoot 'toolchains\lib\OpenHarmony.p12') `
  -keystorePwd 123456 `
  -outFile $signedHap `
  -compatibleVersion 12 `
  -signCode 1

if ($LASTEXITCODE -ne 0) {
  throw 'OpenHarmony HAP signing failed.'
}

Write-Host "Signed OpenHarmony HAP: $signedHap"
