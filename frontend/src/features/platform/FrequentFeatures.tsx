import { FeatureIcon } from "./FeatureIcon";
import { Link } from "react-router-dom";
import { useSession } from "../../app/session";
import { frequentFeatures } from "./featureUsage";

export function FrequentFeatures() {
  const { user } = useSession();
  return (
    <section className="frequent-features" aria-labelledby="frequent-title">
      <div className="section-heading">
        <h2 id="frequent-title">常用功能</h2>
        <small className="muted">最近 30 天</small>
      </div>
      <nav className="frequent-feature-scroll" aria-label="常用功能">
        {frequentFeatures(user!.id).map((item) => (
          <Link key={item.to} to={item.to}>
            <span aria-hidden="true">
              <FeatureIcon name={item.icon} />
            </span>
            <strong>{item.title}</strong>
          </Link>
        ))}
      </nav>
    </section>
  );
}
