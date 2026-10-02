# Module Dependency Graph

## 1. Architectural Layers & Dependency Rules

Dependencies strictly follow a unidirectional hierarchy:
1. **Core / Infrastructure** (`app.core`, `app.db`): Zero domain dependencies.
2. **Domain Models & Schemas** (`app.modules.<domain>.models`, `app.modules.<domain>.schemas`): Only depend on Core & DB.
3. **Data Access (CRUD)** (`app.modules.<domain>.crud`): Depends on domain models and schemas.
4. **Domain Services** (`app.modules.<domain>.service`): Coordinate business rules and trigger cross-cutting domain notifications.
5. **API Presentation** (`app.modules.<domain>.apis`, `app.modules.<domain>.router`): Thin controller layer accepting HTTP requests, invoking services, and returning validated schemas.

---

## 2. Mermaid Module Dependency Diagram

```mermaid
graph TD
    subgraph CoreLayer["Core & Shared Infrastructure"]
        Config["app.core.config"]
        Security["app.core.security"]
        Deps["app.core.dependencies"]
        DBSession["app.db.session (Base, get_db)"]
        DBBase["app.db.base (All 10 Models)"]
        RootRoute["app.core.root (Root /)"]
    end

    subgraph ModulesLayer["Domain Modules (app/modules)"]
        M_Accounts["app.modules.accounts"]
        M_Menu["app.modules.menu"]
        M_Tables["app.modules.tables"]
        M_Sessions["app.modules.sessions"]
        M_Orders["app.modules.orders"]
        M_Dashboard["app.modules.dashboard"]
        M_Settings["app.modules.settings"]
        M_Notifications["app.modules.notifications"]
        M_Health["app.modules.health"]
    end

    subgraph CentralRouter["API Routing"]
        APIRouter["app.api.v1.router.api_router"]
    end

    %% Model registration
    DBBase --> M_Accounts
    DBBase --> M_Menu
    DBBase --> M_Tables
    DBBase --> M_Orders
    DBBase --> M_Sessions
    DBBase --> M_Settings

    %% Dependency arrows
    M_Accounts --> DBSession
    M_Accounts --> Security
    M_Accounts --> Deps

    M_Menu --> DBSession
    M_Menu --> Deps
    M_Menu --> M_Notifications

    M_Tables --> DBSession
    M_Tables --> Security
    M_Tables --> Config
    M_Tables --> M_Notifications
    M_Tables --> M_Sessions

    M_Sessions --> DBSession
    M_Sessions --> Deps
    M_Sessions --> M_Tables
    M_Sessions --> M_Notifications

    M_Orders --> DBSession
    M_Orders --> Deps
    M_Orders --> M_Menu
    M_Orders --> M_Tables
    M_Orders --> M_Sessions
    M_Orders --> M_Notifications

    M_Dashboard --> DBSession
    M_Dashboard --> Deps
    M_Dashboard --> M_Orders
    M_Dashboard --> M_Sessions
    M_Dashboard --> M_Tables

    M_Settings --> DBSession
    M_Settings --> Deps

    M_Notifications --> Security
    M_Health --> DBSession
    M_Health --> Config
    RootRoute --> M_Health

    APIRouter --> M_Accounts
    APIRouter --> M_Menu
    APIRouter --> M_Tables
    APIRouter --> M_Orders
    APIRouter --> M_Sessions
    APIRouter --> M_Dashboard
    APIRouter --> M_Settings
    APIRouter --> M_Notifications
    APIRouter --> M_Health
```
