cask "brewcat" do
  version "0.2.1"
  sha256 "6106dce7b0f5e16f9b263846c70ead589a7d57061122b04b816daca59c618f01"

  url "https://github.com/1985epma/homebrew-brewcat/releases/download/v#{version}/brewcat-#{version}.dmg"
  name "brewcat"
  desc "Visual catalog of Homebrew packages, skills and MCP servers"
  homepage "https://github.com/1985epma/homebrew-brewcat"

  # The .dmg holds a native arm64 binary. On an Intel Mac use the formula, which is built on the machine itself.
  depends_on arch: :arm64
  depends_on :macos

  app "brewcat.app"

  # The app is not notarized by Apple; remove the quarantine flag so it opens without a Gatekeeper warning.
  postflight_steps do
    run "/usr/bin/xattr",
        args:         ["-dr", "com.apple.quarantine", "{{appdir}}/brewcat.app"],
        must_succeed: false
  end

  zap trash: [
    "~/Applications/brewcat.app",
    "~/Library/Application Support/brewcat",
  ]
end
