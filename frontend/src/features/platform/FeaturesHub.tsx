import { FeatureIcon } from "./FeatureIcon";
import { Link } from "react-router-dom";

import { orderedSections, unavailable } from "./features";

export function FeaturesHub() {
  return (
    <main className="page feature-page">
      <header className="platform-header">
        <h1>功能中心</h1>
      </header>
      <nav className="feature-menu" aria-label="生活功能">
        {orderedSections.map((item) =>
          unavailable.has(item.to) ? (
            <button key={item.to} disabled>
              <span aria-hidden="true">
                <FeatureIcon name={item.icon} />
              </span>
              <strong>{item.title}</strong>
              <small>暂未开放</small>
              <b aria-hidden="true">
                <FeatureIcon name="chevron" />
              </b>
            </button>
          ) : (
            <Link key={item.to} to={item.to}>
              <span aria-hidden="true">
                <FeatureIcon name={item.icon} />
              </span>
              <strong>{item.title}</strong>
              <small>{item.text}</small>
              <b aria-hidden="true">
                <FeatureIcon name="chevron" />
              </b>
            </Link>
          ),
        )}
      </nav>
    </main>
  );
}
