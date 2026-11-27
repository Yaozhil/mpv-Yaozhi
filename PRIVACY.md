# Yaoplayer Trakt Privacy Policy

Yaoplayer is a local desktop media player for Windows. Connecting a Trakt account is optional. Yaoplayer accesses your Trakt account only after you choose to connect it and authorize access using OAuth 2.0 with Proof Key for Code Exchange (PKCE).

## Data and purpose

The integration reads your Trakt username to identify the connected account. It sends scrobbles to record playback progress and reads or updates watched history to keep your Trakt viewing activity in sync. Yaoplayer uses this data only to provide the Trakt features you enable.

## Storage and disclosure

Trakt tokens and integration state are stored only on your Windows device in `%LOCALAPPDATA%\Yaoplayer\MediaLibrary\trakt-state.json` and protected using the Windows Data Protection API (DPAPI).

The developer operates no central server for this integration and does not collect or share your Trakt account or playback data. Yaoplayer sends that data only to `api.trakt.tv`. Trakt handles sign-in in your browser. The static OAuth callback page is hosted on GitHub Pages and passes the temporary authorization response to Yaoplayer on the same device. The page uses no analytics, third-party scripts, or developer-operated backend.

## Disconnecting

You can disconnect Trakt in Yaoplayer Settings at any time. Disconnecting immediately clears the locally stored Trakt tokens. You can also revoke Yaoplayer's access at any time from your Trakt account's connected-app settings. Revocation invalidates the authorization on Trakt. To remove the local token copy immediately after revoking access on the website, disconnect in Yaoplayer Settings as well.

## Contact

For privacy questions about this integration, use the [Yaoplayer issue tracker](https://github.com/Yaozhil/mpv-Yaozhi/issues).
