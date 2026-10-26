cask "brewcat" do
  version "0.1.2.6"
  sha256 "1ee0e2a8fd2405399b0eceed94230c80631932ef6f4133270b6f13ccc933dc57"

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
