{
  description = "cleanker — remove comments and unreferenced prose";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = {self, nixpkgs, ...}: let
    systems = ["x86_64-linux" "aarch64-linux"];
    forAll = f: nixpkgs.lib.genAttrs systems (system: f nixpkgs.legacyPackages.${system});
  in {
    packages = forAll (pkgs: let
      cleanker = pkgs.callPackage ./package.nix {};
    in {
      inherit cleanker;
      default = cleanker;
    });

    formatter = forAll (pkgs: pkgs.alejandra);
  };
}
