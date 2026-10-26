cask "brewcat" do
  version "0.1.2.5"
  sha256 "bc8407a011d6fe1ee88d9957da3bfd6845dd14f0e4c12e3d64374a979d0d835b"

  url "https://github.com/1985epma/homebrew-brewcat/releases/download/v#{version}/brewcat-#{version}.dmg"
  name "brewcat"
  desc "Visual catalog of Homebrew packages, skills and MCP servers"
  homepage "https://github.com/1985epma/homebrew-brewcat"

  depends_on formula: "python-tk"

  app "brewcat.app"

  # The app is not notarized by Apple; remove the quarantine flag so it opens without a Gatekeeper warning.
  postflight do
    system_command "/usr/bin/xattr",
                   args: ["-dr", "com.apple.quarantine", "#{appdir}/brewcat.app"],
                   sudo: false
  end

  zap trash: [
    "~/Applications/brewcat.app",
    "~/Library/Application Support/brewcat",
  ]
end
