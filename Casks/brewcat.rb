cask "brewcat" do
  version "0.2.0"
  sha256 "895b35c9fd21cda0bb75e9a5ebba1de30754d2d1f76b174a0e8c8966bc96468a"

  url "https://github.com/1985epma/homebrew-brewcat/releases/download/v#{version}/brewcat-#{version}.dmg"
  name "brewcat"
  desc "Visual catalog of Homebrew packages, skills and MCP servers"
  homepage "https://github.com/1985epma/homebrew-brewcat"

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
