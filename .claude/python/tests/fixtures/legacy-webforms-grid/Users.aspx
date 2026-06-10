<%@ Page Language="C#" AutoEventWireup="true" CodeBehind="Users.aspx.cs" Inherits="HelloWebForms.Users" %>
<!DOCTYPE html>
<html>
<head>
    <title>Gestion des utilisateurs</title>
    <style>
        .grid { border: 1px solid #2563eb; }
        .grid th { background-color: #1e40af; color: #ffffff; font-family: 'Segoe UI', sans-serif; }
    </style>
</head>
<body style="background-color: #f8fafc; padding: 16px;">
    <form id="form1" runat="server">
        <h1>Utilisateurs</h1>

        <asp:DropDownList ID="ddlRole" runat="server">
            <asp:ListItem Value="all">Tous les rôles</asp:ListItem>
            <asp:ListItem Value="admin">Administrateur</asp:ListItem>
            <asp:ListItem Value="user">Utilisateur</asp:ListItem>
        </asp:DropDownList>

        <asp:CheckBox ID="chkActiveOnly" runat="server" Text="Actifs uniquement" />

        <asp:GridView ID="gvUsers" runat="server" CssClass="grid" DataSourceID="sdsUsers" AutoGenerateColumns="false">
            <Columns>
                <asp:BoundField DataField="Id" HeaderText="Identifiant" />
                <asp:BoundField DataField="Username" HeaderText="Nom d'utilisateur" />
                <asp:BoundField DataField="CreatedAt" HeaderText="Créé le" />
                <asp:TemplateField HeaderText="Actions">
                    <ItemTemplate>
                        <asp:LinkButton ID="lnkEdit" runat="server" Text="Éditer"
                            CommandArgument='<%# Eval("Id") %>' />
                    </ItemTemplate>
                </asp:TemplateField>
            </Columns>
        </asp:GridView>

        <asp:Button ID="btnExport" runat="server" Text="Exporter" PostBackUrl="Export.aspx" />
    </form>
</body>
</html>
