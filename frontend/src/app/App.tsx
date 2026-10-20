import { createBrowserRouter, Navigate, Link, Outlet, RouterProvider } from "react-router-dom";
import { Auth } from "../features/auth/Auth";
import { Protected, SessionProvider } from "./session";
import { TodoEditor, TodoList, TodosLayout } from "../features/todos/Todos";
import { Assistant } from "../features/assistant/Assistant";
import { AssistantPreferences } from "../features/assistant/AssistantPreferences";
import { AppShell } from "../features/platform/AppShell";
import { Home } from "../features/platform/Home";
import { Settings } from "../features/platform/Settings";
import { CalendarPage } from "../features/calendar/CalendarPage";
import { EventEditor } from "../features/calendar/EventEditor";
import { Plan } from "../features/calendar/Plan";
import { ChecklistList } from "../features/checklists/ChecklistList";
import { ChecklistDetail } from "../features/checklists/ChecklistDetail";
import { Review } from "../features/review/Review";
import { FeaturesHub } from "../features/platform/FeaturesHub";
import { FamilyPage } from "../features/family/FamilyPage";
import { ContactsPage } from "../features/family/ContactsPage";
import { NotificationsPage } from "../features/family/NotificationsPage";
import { DocumentsPage } from "../features/documents/DocumentsPage";
import { DocumentReviewPage } from "../features/documents/DocumentReviewPage";
import { MealDetailPage } from "../features/life_services/MealDetailPage";
import { MealsPage } from "../features/life_services/MealsPage";
import { NewMealPage } from "../features/life_services/NewMealPage";
import { MealSettingsPage } from "../features/life_services/MealSettingsPage";
import {
  ShoppingDetailRedirect,
  ShoppingListsPage,
} from "../features/life_services/ShoppingListsPage";
import { SearchPage } from "../features/platform/SearchPage";
import { ConnectionsPage } from "../features/platform/ConnectionsPage";
import { ArchiveSearchPage } from "../features/documents/ArchiveSearchPage";
import { VoiceMemosPage } from "../features/assistant/VoiceMemosPage";
import { DailyDump } from "../features/review/DailyDump";
import "../styles/app.css";
import { FormValidationToast } from "../shared/FormValidationToast";
const router = createBrowserRouter([
  {
    element: (
      <SessionProvider>
        <Outlet />
      </SessionProvider>
    ),
    children: [
      { path: "/login", element: <Auth key="login" /> },
      { path: "/register", element: <Auth key="register" register /> },
      {
        element: <Protected />,
        children: [
          {
            element: <AppShell />,
            children: [
              { path: "/", element: <Home /> },
              { path: "/assistant", element: <Assistant /> },
              { path: "/assistant/preferences", element: <AssistantPreferences /> },
              { path: "/settings", element: <Settings /> },
              { path: "/plan", element: <Plan /> },
              { path: "/calendar", element: <CalendarPage /> },
              { path: "/calendar/new", element: <EventEditor /> },
              { path: "/calendar/:id/edit", element: <EventEditor /> },
              { path: "/checklists", element: <ChecklistList /> },
              { path: "/checklists/:id", element: <ChecklistDetail /> },
              { path: "/checklists/shopping/:id", element: <ShoppingDetailRedirect /> },
              { path: "/review", element: <Review /> },
              { path: "/features", element: <FeaturesHub /> },
              { path: "/family", element: <FamilyPage /> },
              { path: "/contacts", element: <ContactsPage /> },
              { path: "/notifications", element: <NotificationsPage /> },
              { path: "/documents", element: <DocumentsPage /> },
              { path: "/document-review", element: <DocumentReviewPage /> },
              { path: "/meals", element: <MealsPage /> },
              { path: "/meals/new", element: <NewMealPage /> },
              { path: "/meals/settings", element: <MealSettingsPage /> },
              { path: "/meals/:id", element: <MealDetailPage /> },
              { path: "/shopping", element: <ShoppingListsPage /> },
              { path: "/shopping/:id", element: <ShoppingDetailRedirect /> },
              { path: "/appointments", element: <Navigate to="/features" replace /> },
              { path: "/search", element: <SearchPage /> },
              { path: "/connections", element: <ConnectionsPage /> },
              { path: "/archive-search", element: <ArchiveSearchPage /> },
              { path: "/voice-memos", element: <VoiceMemosPage /> },
              { path: "/voice-live", element: <Navigate to="/features" replace /> },
              { path: "/daily-dump", element: <DailyDump /> },
              {
                element: <TodosLayout />,
                children: [
                  { path: "/todos", element: <TodoList /> },
                  { path: "/todos/new", element: <TodoEditor /> },
                  { path: "/todos/:id", element: <TodoEditor /> },
                  { path: "/todos/:id/edit", element: <TodoEditor /> },
                ],
              },
            ],
          },
        ],
      },
      {
        path: "*",
        element: (
          <main className="state not-found">
            <h1>页面不存在</h1>
            <Link className="button" to="/">
              返回首页
            </Link>
          </main>
        ),
      },
    ],
  },
]);
export default function App() {
  return (
    <FormValidationToast>
      <RouterProvider router={router} />
    </FormValidationToast>
  );
}
