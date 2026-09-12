$dockerCommand = Get-Command docker -ErrorAction SilentlyContinue
if ($dockerCommand) {
    $dockerExecutable = $dockerCommand.Source
}
else {
    $dockerExecutable = Join-Path $env:LOCALAPPDATA "Programs\DockerDesktop\resources\bin\docker.exe"
}

if (-not (Test-Path -LiteralPath $dockerExecutable)) {
    throw "Docker CLI was not found. Start or reinstall Docker Desktop."
}

& $dockerExecutable @args
exit $LASTEXITCODE
