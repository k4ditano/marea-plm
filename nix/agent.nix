# Her chat's engine: the packages of `agent/` (the Pi SDK), fetched by Nix
# from the lock, with no package's install scripts run. Marea's sandbox runs
# them with the system's Node.
{ buildNpmPackage, nodejs }:
buildNpmPackage {
  pname = "marea-agent";
  version = "0.1.0";
  src = ../agent;
  inherit nodejs;
  npmDepsHash = "sha256-HqxjBrqu7URvJVcka+a0eV8Eb3gAkKPQAyO9AqkAPUo=";
  npmFlags = [ "--ignore-scripts" ];
  dontNpmBuild = true;
  installPhase = ''
    runHook preInstall
    mkdir -p $out
    cp -r node_modules $out/node_modules
    runHook postInstall
  '';
}
