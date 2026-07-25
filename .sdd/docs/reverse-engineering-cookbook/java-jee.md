# Recette — Java EE (Servlet / JSP / JSF)

## Quand l'utiliser

Détection `java-ee` ou `spring-mvc` dans `inventory.json.languagesDetected`. Présence `.java` + `.jsp` ou `.xhtml`, et `web.xml` ou `WEB-INF/`.

## Pré-conditions

- `*.java` (servlets ou managed beans)
- `WEB-INF/web.xml` (config servlets) ou annotations modernes (`@WebServlet`, `@ManagedBean`)
- `*.jsp` / `*.xhtml` (vues)
- `persistence.xml` ou `hibernate.cfg.xml` (mapping DB) — optionnel

## Pièges connus

| Piège | Mitigation Phase 3 |
|---|---|
| Config XML dispersée (`web.xml` + `faces-config.xml` + `applicationContext.xml`) | Phase 2 : lister tous les XML config en entry points |
| EJB legacy (`@Stateless`, `@Stateful`) | Capturer comme composants métier — pas une FEAT mais des dépendances |
| JSF lifecycle (`@PostConstruct`, `@PreDestroy`) | Bias toward present : ne capturer que les méthodes appelées par évènement utilisateur |
| Bean scopes (`@SessionScoped` vs `@RequestScoped`) | Différence sémantique critique pour les ACs — préserver dans BR |
| JNDI lookups | Capturer comme dépendance externe Phase 2 |

## Heuristiques d'extraction

1. **1 servlet `@WebServlet` ≈ 1 unité** ; **1 ManagedBean ≈ 1 unité** sauf si helper transverse
2. AC depuis :
   - `doGet` / `doPost` → 1 AC par chemin observable
   - `@ManagedBean` methods avec attribute `action=` JSF → 1 AC par action
3. BR depuis :
   - `@RolesAllowed` (JAAS) ou `<security-constraint>` web.xml → rôles
   - Bean Validation (`@NotNull`, `@Size`, `@Pattern`)
4. Entities :
   - `@Entity` JPA (avec `@Id` + `@Column`)
   - `persistence.xml` (DB metadata)
   - Hibernate `*.hbm.xml` mappings (legacy)

## Recommandations Phase 5

- Si EJB Stateful présent : noter que la Phase 6 ne reproduira PAS le state (migrer vers JWT + cache)
- `## Project Config` cible : `kotlin-spring-boot` ou `node-express` (Java EE complet n'est plus dans nos stacks cibles)
- Vérifier que tous les `<security-constraint>` du web.xml sont reflétés en BRs

## Exemple

Legacy `LoginServlet.java` :
```java
@WebServlet("/login")
public class LoginServlet extends HttpServlet {
    protected void doPost(HttpServletRequest req, HttpServletResponse resp) throws ServletException, IOException {
        String username = req.getParameter("username");
        String password = req.getParameter("password");
        User user = userDao.findByUsername(username);
        if (user != null && PasswordUtils.verify(password, user.getPasswordHash())) {
            req.getSession().setAttribute("userId", user.getId());
            resp.sendRedirect("home.jsp");
            return;
        }
        req.setAttribute("error", "Identifiants incorrects");
        req.getRequestDispatcher("login.jsp").forward(req, resp);
    }
}
```

Extrait FEAT :
```markdown
- **AC-1** Given username + password valides en table users, when POST /login, then session attribute userId est créée et redirect home.jsp. <!-- evidence: LoginServlet.java:5-10 --> <!-- confidence: high -->
- **AC-2** Given credentials invalides, when POST /login, then attribute "error" propagé et login.jsp re-rendue. <!-- evidence: LoginServlet.java:11-12 --> <!-- confidence: high -->
- **BR-1** Vérification password via PasswordUtils.verify contre PasswordHash. <!-- evidence: LoginServlet.java:7 --> <!-- confidence: high -->
- **BR-2** Username unique en base (contrainte UNIQUE sur table users). <!-- evidence: persistence.xml + entities/User.java:@Column(unique=true) --> <!-- confidence: high -->
```

Confidence cap : `high`.
