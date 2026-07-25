<%@ Page Language="C#" AutoEventWireup="true" CodeBehind="Default.aspx.cs" Inherits="HelloWebForms.Default" %>
<!DOCTYPE html>
<html>
<head runat="server">
    <title>Accueil</title>
</head>
<body>
    <form id="form1" runat="server">
        <h1>Bienvenue</h1>
        <asp:Label ID="lblWelcome" runat="server" Text=""></asp:Label>
        <br />
        <asp:LinkButton ID="lnkLogout" runat="server" OnClick="lnkLogout_Click" Text="Déconnexion" />
    </form>
</body>
</html>
