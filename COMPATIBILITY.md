# OS Pariah Portal Compatibility Matrix

The OS Pariah Portal is fundamentally an enterprise-grade web interface for OpenSimulator databases and RPC endpoints. Because of this tight integration, the portal is sensitive to upstream database schema changes.

Our primary development target and officially supported branch is **NGC-Tranquility** and using the **OS-Pariah Installation** project, as it aligns with the enterprise best practices this portal is built upon.

While the portal *may* work with standard OpenSimulator Core or other forks, we do not officially guarantee support or write custom database fallback queries for them. If a version is listed as compatible below, it means it has been tested and verified to work.  We may also add information about various efforts to patch for other versions if we are made aware of them and they continue to provide the level of functionality and stability that we are striving for.

## 📊 Supported Versions

| OS Pariah Portal | NGC-Tranquility | Status | Notes |
| :--- | :--- | :--- | :--- |
| **v1.0.1** | 🟢`v0.9.3.9333` | 🟢Active | Current stable release (security/deps + Platform Standards). |
| **v1.0.0** | 🟢`v0.9.3.9333` | 🟢Supported | First stable release. |
| **v0.10.1** | 🟢`v0.9.3.9333` | 🟡Beta | Beta release (not tagged; see v1.0.0). |
| **v0.10.0** | 🟢`v0.9.3.9333` | 🟡Beta | Beta Release. |
| **v0.9.4** | 🟢`v0.9.3.9333` | 🟡Beta | Beta Release. |
| **v0.9.3** | 🔴 | 🔴 Abandoned | Critically failed release testing, dropped. |
| **v0.9.2** | 🟢`v0.9.3.9333` | 🟡Beta | Beta Release. |
| **v0.9.0 - v0.9.1** | 🟡`v0.9.3.9333`<br />⚪`v0.9.3.9254` | 🟡Beta | Initial post-alpha Release. |
| **v0.x.x** | 🔴Pre-Tranquility | 🔴Legacy | Alpha source - Testing and POC releases. |

Legend: 🟢Supported, 🟡Partially functional, ⚪Untested but should be fully to partially functional, 🔴Not Functional

## 🔍 How Compatibility is Determined
The OS Pariah Portal relies on specific structures within the `robust` database (EG: the `useraccounts`, `griduser`, or `auth` tables) as well as standard Gatekeeper logging formats. 

If an upstream OpenSimulator update alters these database schemas or removes required XML-RPC endpoints, compatibility will break. We will update this matrix as we test new upstream releases.

## 🛠️ Using Unsupported Versions
If you are running a grid on an unlisted or unsupported version of OpenSimulator (such as an older Core fork), the portal may still install correctly, but you may experience issues like, but not limited to:
* 500 Server Errors during login or registration.
* Missing functions integrated.
* Incorrect function access.
* Failed configuration coordination.
* Failures in the background IAR backup worker.
* Inaccurate online user counts.

If you successfully run OS Pariah on an unlisted version, please open an Issue on GitHub so we can update this matrix!
