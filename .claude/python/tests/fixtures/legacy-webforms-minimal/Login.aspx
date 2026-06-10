<%@ Page Language="C#" AutoEventWireup="true" CodeBehind="Login.aspx.cs" Inherits="HelloWebForms.Login" %>
<!DOCTYPE html>
<html>
<head runat="server">
    <title>Connexion</title>
</head>
<body>
    <form id="form1" runat="server" method="post">
        <h1>Connexion</h1>
        <asp:Label runat="server" Text="Nom d'utilisateur :" AssociatedControlID="txtUsername" />
        <asp:TextBox ID="txtUsername" runat="server" />
        <br />
        <asp:Label runat="server" Text="Mot de passe :" AssociatedControlID="txtPassword" />
        <asp:TextBox ID="txtPassword" runat="server" TextMode="Password" />
        <br />
        <asp:Button ID="btnLogin" runat="server" Text="Se connecter" OnClick="btnLogin_Click" />
        <br />
        <asp:Label ID="lblError" runat="server" ForeColor="Red" Text="" />
    </form>
</body>
</html>
