{ pkgs ? import <nixpkgs> {} }:
(pkgs.buildFHSUserEnv {
  name = "pipzone";
  targetPkgs = pkgs: (with pkgs; [
    python310
    python310Packages.pip
    python310Packages.virtualenv
  ]);
  runScript = "bash";
}).env

/* To use this:
nix-shell pip-shell.nix
(first time) virtualenv .venv
source .venv/bin/activate
*/
