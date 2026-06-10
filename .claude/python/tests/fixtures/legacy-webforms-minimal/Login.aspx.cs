using System;
using System.Web.UI;
using HelloWebForms.App_Code;

namespace HelloWebForms
{
    public partial class Login : Page
    {
        protected void Page_Load(object sender, EventArgs e)
        {
            if (!IsPostBack)
            {
                lblError.Text = string.Empty;
            }
        }

        protected void btnLogin_Click(object sender, EventArgs e)
        {
            string username = txtUsername.Text.Trim();
            string password = txtPassword.Text;

            int? userId = DataAccess.ValidateUser(username, password);
            if (userId.HasValue)
            {
                Session["UserId"] = userId.Value;
                Response.Redirect("Default.aspx");
            }
            else
            {
                lblError.Text = "Identifiants incorrects";
            }
        }
    }
}
